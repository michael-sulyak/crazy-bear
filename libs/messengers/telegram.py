import datetime
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
from telegram import InputMediaPhoto, ReplyKeyboardMarkup, Update as TelegramUpdate
from telegram.constants import ChatAction, ParseMode
from telegram.error import (
    NetworkError as TelegramNetworkError,
)

from project import config
from .base import BaseMessenger, ChatInfo, MessageInfo, UserInfo
from .mixins import CVMixin
from .utils import escape_markdown
from ..casual_utils.aio import async_to_sync
from ..casual_utils.parallel_computing import synchronized_method
from ..casual_utils.time import get_current_time


__all__ = ('TelegramMessenger',)

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
    default_reply_markup: typing.Callable | None
    _bot: telegram.Bot
    _updates_offset: typing.Optional[int] = None
    _lock: threading.RLock
    _update_queue: queue.Queue
    _worker: threading.Thread
    _last_message_id: typing.Any = None
    _last_sent_at: typing.Optional[datetime.datetime] = None
    _message_handler: typing.Callable

    def __init__(
        self, *, message_handler: typing.Callable, default_reply_markup: typing.Callable | None = None
    ) -> None:
        self.default_reply_markup = default_reply_markup
        self._bot = telegram.Bot(token=config.TELEGRAM_TOKEN)
        self._lock = threading.RLock()
        self._update_queue = queue.Queue()
        self._run_worker()
        self._message_handler = message_handler

    @property
    @synchronized_method
    def last_message_id(self) -> typing.Any:
        return self._last_message_id

    @property
    @synchronized_method
    def last_sent_at(self) -> typing.Optional[datetime.datetime]:
        return self._last_sent_at

    @synchronized_method
    def close(self) -> None:
        self._worker.join(0)

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def send_message(
        self,
        text: str,
        *,
        use_markdown: bool = False,
        reply_markup: ReplyKeyboardMarkup | typing.Type[DEFAULT] | None = DEFAULT,
        message_id: int | None = None,
    ) -> typing.Optional[int]:
        if reply_markup is DEFAULT:
            if callable(self.default_reply_markup):
                reply_markup = self.default_reply_markup()
            else:
                reply_markup = self.default_reply_markup

        if message_id:
            func = partial(self._bot.edit_message_text, message_id=message_id)
        else:
            func = self._bot.send_message

        result = await func(
            chat_id=self.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2 if use_markdown else None,
            reply_markup=reply_markup,
        )

        self._last_message_id = message_id or result.message_id
        self._last_sent_at = get_current_time()

        return message_id or result.message_id

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def send_image(self, image: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        result = await self._bot.send_photo(
            self.chat_id,
            photo=image,
            caption=caption,
        )
        self._last_message_id = result.message_id
        self._last_sent_at = get_current_time()

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def send_images(self, images: typing.Any) -> None:
        if not images:
            return

        results = await self._bot.send_media_group(
            self.chat_id,
            media=list(InputMediaPhoto(media=image) for image in images),
        )

        self._last_message_id = results[-1].message_id
        self._last_sent_at = get_current_time()

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def send_file(self, file: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        result = await self._bot.send_document(
            self.chat_id,
            document=file,
            caption=caption,
        )
        self._last_message_id = result.message_id
        self._last_sent_at = get_current_time()

    def error(self, text: str, *, title: str = 'Error') -> None:
        logging.warning(text)
        self.send_message(
            f'{emojize(":pager:")} ️*{title}* ```\n{escape_markdown(text, entity_type="pre")}\n```',
            use_markdown=True,
        )

    def exception(self, exp: Exception) -> None:
        self.error(
            f'{repr(exp)}\n{"".join(traceback.format_tb(exp.__traceback__))}',
            title='Exception',
        )

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def start_typing(self) -> None:
        await self._bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)

    @synchronized_method
    @handel_telegram_exceptions
    @async_to_sync
    async def remove_message(self, message_id: int) -> None:
        await self._bot.delete_message(chat_id=self.chat_id, message_id=message_id)

        if self._last_message_id == message_id:
            self._last_message_id = None

    def _run_worker(self) -> None:
        def _worker() -> typing.NoReturn:
            connection = None
            while connection is None:
                try:
                    connection = pika.BlockingConnection(
                        pika.ConnectionParameters(host=config.TELEHOOKS_HOST, heartbeat=600),
                    )
                except AMQPConnectionError as e:
                    logging.warning(e)
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
        if (
            update.effective_user is None
            or update.edited_message is not None
            or update.effective_chat is None
            or update.message is None
            or not isinstance(update.message.text, str)
        ):
            return

        message = MessageInfo(
            user=UserInfo(
                name=update.effective_user.name,
                username=update.effective_user.username,
            ),
            chat=ChatInfo(
                id=update.effective_chat.id,
            ),
            text=update.message.text,
        )

        self._message_handler(message, messanger=self)
