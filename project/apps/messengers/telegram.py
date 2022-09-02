import functools
import json
import logging
import queue
import threading
import traceback
import typing
from functools import partial
from time import sleep

import pika
import telegram
import urllib3
from emoji import emojize
from pika.exceptions import AMQPConnectionError
from telegram import ReplyMarkup, Update as TelegramUpdate
from telegram.error import (
    NetworkError as TelegramNetworkError,
)
from telegram.ext.utils.webhookhandler import WebhookServer
from telegram.utils.request import Request as TelegramRequest

from . import events
from .base import BaseMessenger
from .mixins import CVMixin
from .utils import escape_markdown
from ..common.utils import synchronized_method
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


def handel_telegram_exceptions(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrap_func(*args, **kwargs) -> typing.Any:
        try:
            return func(*args, **kwargs)
        except TelegramNetworkError as e:
            if isinstance(e.__cause__, urllib3.exceptions.HTTPError):
                logging.warning(e, exc_info=True)
                return None

            raise

    return wrap_func


class TelegramMessenger(CVMixin, BaseMessenger):
    chat_id: int = config.TELEGRAM_CHAT_ID
    default_reply_markup: typing.Optional
    _bot: telegram.Bot
    _updates_offset: typing.Optional[int] = None
    _lock: threading.RLock
    _update_queue: queue.Queue
    _webhook_server: WebhookServer
    _worker: threading.Thread
    _last_message_id: typing.Any = None

    def __init__(self, *,
                 request: typing.Optional[TelegramRequest] = None,
                 default_reply_markup: typing.Optional = None) -> None:
        self.default_reply_markup = default_reply_markup
        self._bot = telegram.Bot(
            token=config.TELEGRAM_TOKEN,
            request=request,
        )
        self._lock = threading.RLock()
        self._update_queue = queue.Queue()
        self._run_worker()

    @property
    @synchronized_method
    def last_message_id(self) -> typing.Any:
        return self._last_message_id

    def close(self) -> None:
        self._worker.join(0)

    @synchronized_method
    @handel_telegram_exceptions
    def send_message(self,
                     text: str, *,
                     use_markdown: bool = False,
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

        result = func(
            chat_id=self.chat_id,
            text=text,
            parse_mode='MarkdownV2' if use_markdown else None,
            reply_markup=reply_markup,
        )

        self._last_message_id = message_id or result.message_id

        return message_id or result.message_id

    @synchronized_method
    @handel_telegram_exceptions
    def send_image(self, image: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        result = self._bot.send_photo(
            self.chat_id,
            photo=image,
            caption=caption,
        )
        self._last_message_id = result.message_id

    @synchronized_method
    @handel_telegram_exceptions
    def send_images(self, images: typing.Any) -> None:
        if not images:
            return

        results = self._bot.send_media_group(
            self.chat_id,
            media=list(telegram.InputMediaPhoto(image) for image in images),
        )

        self._last_message_id = results[-1].message_id

    @synchronized_method
    @handel_telegram_exceptions
    def send_file(self, file: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        result = self._bot.send_document(
            self.chat_id,
            document=file,
            caption=caption,
        )
        self._last_message_id = result.message_id

    def error(self, text: str, *, title: str = 'Error') -> None:
        logging.warning(text)
        self.send_message(
            f'{emojize(":pager:")} ️*{title}* ```\n{escape_markdown(text, entity_type="pre")}\n```',
            use_markdown=True,
        )

    def exception(self, exp: Exception) -> None:
        self.error(f'{repr(exp)}\n{"".join(traceback.format_tb(exp.__traceback__))}', title='Exception')

    @synchronized_method
    @handel_telegram_exceptions
    def start_typing(self) -> None:
        self._bot.send_chat_action(chat_id=self.chat_id, action=telegram.ChatAction.TYPING)

    @synchronized_method
    @handel_telegram_exceptions
    def remove_message(self, message_id: int) -> None:
        self._bot.delete_message(chat_id=self.chat_id, message_id=message_id)

    def _run_worker(self) -> None:
        def _worker() -> typing.NoReturn:
            connection = None
            while connection is None:
                try:
                    connection = pika.BlockingConnection(
                        pika.ConnectionParameters(host=config.TELEHOOKS_HOST, heartbeat=600),
                    )
                except AMQPConnectionError as e:
                    logging.error(e)
                    logging.info('Waiting AMQP...')
                    sleep(1)

            channel = connection.channel()

            def _callback(ch, method, properties, body: bytes):
                telegram_update = TelegramUpdate.de_json(
                    data=json.loads(body.decode('utf-8')),
                    bot=self._bot,
                )

                try:
                    self._process_telegram_message(telegram_update)
                except Exception as e:
                    logging.exception(e)

            channel.queue_declare(queue=config.TELEHOOKS_QUEUE_NAME)
            channel.basic_consume(queue=config.TELEHOOKS_QUEUE_NAME, on_message_callback=_callback, auto_ack=True)
            channel.start_consuming()

        self._worker = threading.Thread(target=_worker)
        self._worker.start()

    def _process_telegram_message(self, update: TelegramUpdate) -> None:
        username = update.message and update.message.from_user and update.message.from_user.username

        if username != config.TELEGRAM_USERNAME:
            text = update.message.text.replace("`", "\\`")
            self.error(
                f'User "{update.effective_user.name}" (@{update.effective_user.username}) sent '
                f'in chat #{update.effective_chat.id}:\n'
                f'```\n{text}\n```'
            )
            return

        events.new_message.send(message=self._parse_update(update))

    @staticmethod
    def _parse_update(update: TelegramUpdate) -> Message:
        return Message(
            username=update.message.from_user.username,
            chat_id=update.message.chat_id,
            text=update.message.text,
            command=Command.from_string(update.message.text),
        )
