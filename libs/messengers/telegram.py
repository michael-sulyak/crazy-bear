import asyncio
import datetime
import functools
import json
import logging
import queue
import random
import threading
import traceback
import typing
from collections import OrderedDict
from functools import partial

import httpx
import pika
import telegram
import urllib3
from emoji import emojize
from pika.exceptions import AMQPError
from sentry_sdk import metrics
from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardMarkup, InputMediaPhoto, ReplyKeyboardMarkup
from telegram import Update as TelegramUpdate
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.error import NetworkError as TelegramNetworkError
from telegram.request import HTTPXRequest

from project import config

from ..casual_utils.aio import async_to_sync
from ..casual_utils.parallel_computing import synchronized_method
from ..casual_utils.time import get_current_time
from .base import BaseMessenger, ChatInfo, MessageInfo, UserInfo
from .mixins import CVMixin
from .utils import escape_markdown


__all__ = ('TelegramMessenger',)

WEBHOOK_SSL_PEM = './certificate/cert.pem'
WEBHOOK_SSL_KEY = './certificate/private.key'
WEBHOOK_PORT = 8443


class DEFAULT:
    pass


def capture_text_feedback(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrapper(self, text: str, **kwargs):
        # Explicit markup identifies status/progress messages, not routine replies.
        if (
            kwargs.get('message_id') is None
            and kwargs.get('reply_markup', DEFAULT) is DEFAULT
            and self.record_feedback(text)
        ):
            return None

        return func(self, text, **kwargs)

    return wrapper


def handel_telegram_exceptions(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrap_func(*args, **kwargs) -> typing.Any:
        try:
            return func(*args, **kwargs)
        except TelegramNetworkError as e:
            if isinstance(e.__cause__, (urllib3.exceptions.HTTPError, httpx.HTTPError)):
                logging.warning('Issue with network while sending to Telegram', exc_info=True)
                return None

            raise

    return wrap_func


class CustomHTTPXRequest(HTTPXRequest):
    async def do_request(self, *args, **kwargs):
        max_attempts = 3
        base_delay = 0.5
        max_delay = 10

        for attempt in range(1, max_attempts + 1):
            try:
                return await super().do_request(*args, **kwargs)
            except TelegramNetworkError:
                metrics.count('telegram.network.error', 1)

                if attempt >= max_attempts:
                    logging.warning(
                        'Telegram HTTP request failed (%s/%s)',
                        attempt, max_attempts,
                        exc_info=True,
                    )
                    raise

                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                delay *= random.uniform(0.7, 1.3)

                logging.warning(
                    'Telegram HTTP request failed, retry %s/%s in %.2fs',
                    attempt, max_attempts, delay,
                    exc_info=True,
                )

                await asyncio.sleep(delay)


class TelegramMessenger(CVMixin, BaseMessenger):
    chat_id: int = config.TELEGRAM_CHAT_ID
    default_reply_markup: typing.Callable | None
    _bot: telegram.Bot
    _updates_offset: int | None = None
    _lock: threading.RLock
    _update_queue: queue.Queue
    _worker: threading.Thread
    _last_message_id: typing.Any = None
    _last_sent_at: datetime.datetime | None = None
    _message_handler: typing.Callable

    def __init__(
        self, *, message_handler: typing.Callable, default_reply_markup: typing.Callable | None = None,
        callback_commands: typing.Mapping[str, str] | None = None,
    ) -> None:
        self.default_reply_markup = default_reply_markup
        self._callback_commands = dict(callback_commands or {})
        self._bot_username: str | None = None
        self._navigation_ready = False
        self._callback_ids: OrderedDict[str, None] = OrderedDict()
        telegram_request = CustomHTTPXRequest(
            connect_timeout=10,
            read_timeout=60,
            write_timeout=30,
            pool_timeout=10,
            connection_pool_size=20,
            proxy=config.PROXY,
        )
        self._bot = telegram.Bot(
            token=config.TELEGRAM_TOKEN,
            request=telegram_request,
            get_updates_request=telegram_request,
        )
        self._lock = threading.RLock()
        self._update_queue = queue.Queue()
        self._message_handler = message_handler
        self._stop_event = threading.Event()
        self._run_worker()

    @property
    @synchronized_method
    def last_message_id(self) -> typing.Any:
        return self._last_message_id

    @property
    @synchronized_method
    def last_sent_at(self) -> datetime.datetime | None:
        return self._last_sent_at

    def close(self) -> None:
        self._stop_event.set()
        self._worker.join(timeout=15)

        if self._worker.is_alive():
            logging.warning('Telegram consumer did not stop within 15 seconds')

        self._shutdown_bot()

    @capture_text_feedback
    @synchronized_method
    @async_to_sync
    async def send_message(
        self,
        text: str,
        *,
        use_markdown: bool = False,
        reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | type[DEFAULT] | None = DEFAULT,
        message_id: int | None = None,
    ) -> int | None:
        # Telegram only accepts inline keyboards on edited messages.
        if message_id is not None:
            if not isinstance(reply_markup, InlineKeyboardMarkup):
                reply_markup = None
        elif reply_markup is DEFAULT:
            if callable(self.default_reply_markup):
                reply_markup = self.default_reply_markup()
            else:
                reply_markup = self.default_reply_markup

        if message_id is not None:
            func = partial(self._bot.edit_message_text, message_id=message_id)
        else:
            func = self._bot.send_message

        try:
            result = await func(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2 if use_markdown else None,
                reply_markup=reply_markup,
            )
        except BadRequest as exc:
            if message_id is None or not str(exc).casefold().startswith('message is not modified'):
                logging.info('Telegram rejected message in chat %s (message_id=%s): %s', self.chat_id, message_id, exc)
                raise

            # The requested content already exists, including after an HTTP retry.
            result = None
        except Exception:
            logging.info('Not sent telegram message: %s', text)
            raise

        self._last_message_id = message_id if message_id is not None else result.message_id
        self._last_sent_at = get_current_time()

        return self._last_message_id

    @synchronized_method
    # @handel_telegram_exceptions
    @async_to_sync
    async def send_image(self, image: typing.Any, *, caption: str | None = None) -> None:
        result = await self._bot.send_photo(
            self.chat_id,
            photo=image,
            caption=caption,
        )
        self._last_message_id = result.message_id
        self._last_sent_at = get_current_time()

    @synchronized_method
    @async_to_sync
    async def send_video(self, video: typing.BinaryIO, *, caption: str | None = None) -> None:
        result = await self._bot.send_video(self.chat_id, video=video, caption=caption)
        self._last_message_id = result.message_id
        self._last_sent_at = get_current_time()

    @synchronized_method
    @async_to_sync
    async def send_images(self, images: typing.Any) -> None:
        if not images:
            return

        images = tuple(images)

        for start in range(0, len(images), 10):
            batch = images[start: start + 10]

            if len(batch) == 1:
                result = await self._bot.send_photo(
                    self.chat_id,
                    photo=batch[0],
                )
                self._last_message_id = result.message_id
            else:
                results = await self._bot.send_media_group(
                    self.chat_id,
                    media=[InputMediaPhoto(media=image) for image in batch],
                )
                self._last_message_id = results[-1].message_id

            self._last_sent_at = get_current_time()

    @synchronized_method
    # @handel_telegram_exceptions
    @async_to_sync
    async def send_file(self, file: typing.Any, *, caption: str | None = None) -> None:
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
            f'{emojize(":pager:")} *{title}* ```\n{escape_markdown(text, entity_type="pre")}\n```',
            use_markdown=True,
            reply_markup=None,
        )

    def warning(self, text: str) -> None:
        logging.warning(text)
        self.send_message(
            f'{emojize(":warning:")} *Warning* ```\n{escape_markdown(text, entity_type="pre")}\n```',
            use_markdown=True,
            reply_markup=None,
        )

    def exception(self, exp: Exception) -> None:
        self.error(
            f'{exp!r}\n{"".join(traceback.format_tb(exp.__traceback__))}',
            title='Exception',
        )

    @synchronized_method
    # @handel_telegram_exceptions
    @async_to_sync
    async def start_typing(self) -> None:
        await self._bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)

    @synchronized_method
    # @handel_telegram_exceptions
    @async_to_sync
    async def remove_message(self, message_id: int) -> None:
        await self._bot.delete_message(chat_id=self.chat_id, message_id=message_id)

        if self._last_message_id == message_id:
            self._last_message_id = None

    @synchronized_method
    def ensure_navigation(self, *, force: bool = False) -> None:
        if self._navigation_ready and not force:
            return
        markup = self.default_reply_markup() if callable(self.default_reply_markup) else self.default_reply_markup
        if not isinstance(markup, ReplyKeyboardMarkup):
            return

        # Note: Telegram cannot attach reply and inline keyboards to the same message.
        self.send_message('Welcome to the club!', reply_markup=markup)
        self._navigation_ready = True

    @synchronized_method
    @async_to_sync
    async def set_commands(self, commands: typing.Sequence[BotCommand]) -> None:
        # Telegram adds @botname to command-menu selections in group chats.
        identity = await self._bot.get_me()
        self._bot_username = identity.username.casefold() if identity.username else None
        await self._bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeChat(chat_id=self.chat_id),
        )

    @async_to_sync
    async def _answer_callback(self, query_id: str, *, text: str | None = None) -> None:
        # Do not wait for the outbound-message lock: a photo upload may hold it.
        await self._bot.answer_callback_query(
            callback_query_id=query_id,
            text=text,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            pool_timeout=5,
        )

    def _run_worker(self) -> None:
        def _callback(ch, method, properties, body: bytes) -> None:
            try:
                telegram_update = TelegramUpdate.de_json(
                    data=json.loads(body.decode('utf-8')),
                    bot=self._bot,
                )
                if telegram_update is not None:
                    self._process_telegram_message(telegram_update)
            except Exception:
                # A malformed message must not kill the consumer or loop forever.
                logging.exception('Cannot process Telegram update')
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            else:
                ch.basic_ack(delivery_tag=method.delivery_tag)

        def _worker() -> None:
            while not self._stop_event.is_set():
                connection = None
                try:
                    connection = pika.BlockingConnection(
                        pika.ConnectionParameters(
                            host=config.TELEHOOKS_HOST,
                            heartbeat=60,
                            socket_timeout=5,
                            stack_timeout=10,
                            blocked_connection_timeout=10,
                            connection_attempts=1,
                        ),
                    )
                    channel = connection.channel()
                    channel.queue_declare(queue=config.TELEHOOKS_QUEUE_NAME)
                    channel.basic_qos(prefetch_count=1)
                    channel.basic_consume(
                        queue=config.TELEHOOKS_QUEUE_NAME,
                        on_message_callback=_callback,
                        auto_ack=False,
                    )
                    while not self._stop_event.is_set():
                        connection.process_data_events(time_limit=1)
                except (AMQPError, OSError):
                    if not self._stop_event.is_set():
                        logging.warning('Telegram queue connection lost; reconnecting', exc_info=True)
                finally:
                    if connection is not None and connection.is_open:
                        try:
                            connection.close()
                        except (AMQPError, OSError):
                            logging.warning('Cannot close Telegram queue connection', exc_info=True)

                self._stop_event.wait(2)

        self._worker = threading.Thread(target=_worker, name='telegram-consumer', daemon=True)
        self._worker.start()

    def _process_telegram_message(self, update: TelegramUpdate) -> None:
        callback_message_id = None

        if query := update.callback_query:
            text = self._callback_commands.get(query.data) if isinstance(query.data, str) else None
            usable = (
                text is not None
                and update.effective_user is not None
                and update.effective_chat is not None
                and isinstance(query.message, telegram.Message)
            )

            try:
                # Acknowledge promptly, before queued commands or device I/O.
                self._answer_callback(
                    query.id,
                    text=None if usable else 'This button is no longer available. Open /status.',
                )
            except TelegramError:
                # An expired query or failed acknowledgement must not lose the action.
                logging.warning('Cannot acknowledge Telegram button', exc_info=True)

            if not usable or query.id in self._callback_ids:
                return

            # RabbitMQ may redeliver an update if its acknowledgement was lost.
            # Do not repeat relative brightness changes or restart a heating pause.
            self._callback_ids[query.id] = None

            if len(self._callback_ids) > 1024:
                self._callback_ids.popitem(last=False)

            callback_message_id = query.message.message_id
        else:
            if (
                update.effective_user is None
                or update.edited_message is not None
                or update.effective_chat is None
                or update.message is None
                or not isinstance(update.message.text, str)
            ):
                return

            text = update.message.text

            if text.startswith('/'):
                parts = text.split(maxsplit=1)
                command_name, separator, recipient = parts[0].partition('@')
                if separator:
                    # Fail closed before identity is known, and ignore other bots.
                    if not self._bot_username or recipient.casefold() != self._bot_username:
                        return

                    text = ' '.join((command_name, *parts[1:]))

        message = MessageInfo(
            user=UserInfo(
                name=update.effective_user.name,
                username=update.effective_user.username,
                id=update.effective_user.id,
            ),
            chat=ChatInfo(
                id=update.effective_chat.id,
            ),
            text=text,
            callback_message_id=callback_message_id,
        )

        self._message_handler(message, messanger=self)

    @synchronized_method
    @async_to_sync
    async def _shutdown_bot(self) -> None:
        await self._bot.request.shutdown()
