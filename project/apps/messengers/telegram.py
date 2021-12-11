import logging
import os
import queue
import ssl
import threading
import traceback
import typing
import uuid
from functools import partial
from time import sleep

import telegram
from emoji import emojize
from telegram import ReplyMarkup, Update as TelegramUpdate
from telegram.error import NetworkError as TelegramNetworkError, TimedOut as TelegramTimedOut
from telegram.ext.utils.webhookhandler import WebhookAppClass, WebhookServer
from telegram.utils.request import Request as TelegramRequest

from .base import BaseMessenger
from .mixins import CVMixin
from ..common.utils import get_my_ip, synchronized_method
from ..core.base import Command, Message
from ... import config


__all__ = (
    'TelegramMessenger',
)

WEBHOOK_SSL_PEM = './certificate/cert.pem'
WEBHOOK_SSL_KEY = './certificate/private.key'
WEBHOOK_PORT = 8443


class DEFAULT:
    pass


class TelegramMessenger(CVMixin, BaseMessenger):
    chat_id: int = config.TELEGRAM_CHAT_ID
    default_reply_markup: typing.Optional
    _bot: telegram.Bot
    _updates_offset: typing.Optional[int] = None
    _lock: threading.RLock
    _update_queue: queue.Queue
    _webhook_server: WebhookServer
    _server_worker: threading.Thread

    def __init__(self, *,
                 request: typing.Optional[TelegramRequest] = None,
                 default_reply_markup: typing.Optional = None) -> None:
        self._bot = telegram.Bot(
            token=config.TELEGRAM_TOKEN,
            request=request,
        )
        self._lock = threading.RLock()
        self.default_reply_markup = default_reply_markup
        self._update_queue = queue.Queue()
        self._start_webhook_server()

    def _start_webhook_server(self) -> None:
        ip = get_my_ip()
        endpoint_for_webhook = str(uuid.uuid4())

        os.system(
            f'openssl req -newkey rsa:2048 -sha256 -nodes -keyout {WEBHOOK_SSL_KEY} -x509 -days 365 '
            f'-out {WEBHOOK_SSL_PEM} -subj "/C=US/ST=New York/L=Brooklyn/O=Example Brooklyn Company/CN={ip}" '
            f'v>/dev/null 2>&1'
        )

        webhook_url = f'https://{ip}:{WEBHOOK_PORT}/{endpoint_for_webhook}'

        logging.info('Starting webhook on %s...', webhook_url)

        def _worker() -> typing.NoReturn:
            webhook_app = WebhookAppClass(
                webhook_path=f'/{endpoint_for_webhook}',
                bot=self._bot,
                update_queue=self._update_queue,
            )

            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(certfile=WEBHOOK_SSL_PEM, keyfile=WEBHOOK_SSL_KEY)

            self._webhook_server = WebhookServer(
                listen='0.0.0.0',
                port=WEBHOOK_PORT,
                webhook_app=webhook_app,
                ssl_ctx=ssl_ctx,
            )

            with open(WEBHOOK_SSL_PEM, 'rb') as cert_file:
                self._bot.set_webhook(
                    url=webhook_url,
                    certificate=cert_file,
                    ip_address=ip,
                    drop_pending_updates=True,
                    max_connections=40,
                )

            self._webhook_server.serve_forever()

        self._server_worker = threading.Thread(target=_worker)
        self._server_worker.start()

    def close(self) -> None:
        self._webhook_server.shutdown()
        self._server_worker.join()

    @synchronized_method
    def send_message(self, text: str, *,
                     parse_mode: str = 'markdown',
                     reply_markup: typing.Optional[ReplyMarkup] = DEFAULT,
                     message_id: typing.Optional[int] = None) -> typing.Optional[int]:
        if reply_markup is DEFAULT:
            if callable(self.default_reply_markup):
                reply_markup = self.default_reply_markup()
            else:
                reply_markup = self.default_reply_markup

        if message_id:
            func = partial(self._bot.edit_message_text, message_id=message_id)
        else:
            func = self._bot.send_message

        try:
            result = func(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)
            return None

        return message_id or result.message_id

    @synchronized_method
    def send_image(self, image: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        try:
            self._bot.send_photo(
                self.chat_id,
                photo=image,
                caption=caption,
            )
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized_method
    def send_images(self, images: typing.Any) -> None:
        if not images:
            return

        try:
            self._bot.send_media_group(
                self.chat_id,
                media=list(telegram.InputMediaPhoto(image) for image in images),
            )
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized_method
    def send_file(self, file: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        try:
            self._bot.send_document(
                self.chat_id,
                document=file,
                caption=caption,
            )
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized_method
    def error(self, text: str, *, _title: str = 'Error') -> None:
        logging.warning(text)
        self.send_message(f'{emojize(":pager:")} ️*{_title}* ```\n{text}\n```')

    @synchronized_method
    def exception(self, exp: Exception) -> None:
        self.error(f'{repr(exp)}\n{"".join(traceback.format_tb(exp.__traceback__))}', _title='Exception')

    @synchronized_method
    def start_typing(self) -> None:
        try:
            self._bot.send_chat_action(chat_id=self.chat_id, action=telegram.ChatAction.TYPING)
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized_method
    def get_updates(self) -> typing.Iterator[Message]:
        # now = datetime.datetime.now()

        while True:
            try:
                update = self._update_queue.get(block=False)
            except queue.Empty:
                break

            if update.message.from_user.username != config.TELEGRAM_USERNAME:
                text = update.message.text.replace("`", "\\`")
                self.error(
                    f'User "{update.effective_user.name}" (@{update.effective_user.username}) sent '
                    f'in chat #{update.effective_chat.id}:\n'
                    f'```\n{text}\n```'
                )
                continue

            # See drop_pending_updates=True,
            # sent_at = update.message.date.astimezone(config.PY_TIME_ZONE).replace(tzinfo=None)
            #
            # if now - sent_at < datetime.timedelta(seconds=30):
            #     yield self._parse_update(update)
            # else:
            #     logging.debug(f'Skip telegram message: {update.message.text}')
            yield self._parse_update(update)

    @staticmethod
    def _parse_update(update: TelegramUpdate) -> Message:
        text: str = update.message.text

        params = text.split(' ')
        command_name = params[0]
        command_params = tuple(param.strip() for param in params[1:] if param)
        command_args = []
        command_kwargs = {}

        for i, command_param in enumerate(command_params):
            if '=' in command_param:
                name, value = command_param.split('=', 1)
                command_kwargs[name] = value
            else:
                command_args.append(command_param)

        return Message(
            username=update.message.from_user.username,
            chat_id=update.message.chat_id,
            text=text,
            command=Command(
                name=command_name,
                args=command_args,
                kwargs=command_kwargs,
            ),
        )

    def remove_message(self, message_id: int) -> None:
        try:
            self._bot.delete_message(chat_id=self.chat_id, message_id=message_id)
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)
