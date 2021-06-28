import datetime
import logging
import threading
import traceback
import typing
from time import sleep

import telegram
from emoji import emojize
from telegram import Update as TelegramUpdate
from telegram.error import NetworkError as TelegramNetworkError, TimedOut as TelegramTimedOut
from telegram.utils.request import Request as TelegramRequest

from .base import BaseMessenger
from .mixins import CVMixin
from ..common.utils import synchronized
from ..core.base import Command, Message
from ... import config


class TelegramMessenger(CVMixin, BaseMessenger):
    chat_id: int = config.TELEGRAM_CHAT_ID
    default_reply_markup: typing.Optional
    _bot: telegram.Bot
    _updates_offset: typing.Optional[int] = None
    _lock: threading.RLock

    def __init__(self, *,
                 request: typing.Optional[TelegramRequest] = None,
                 default_reply_markup: typing.Optional = None) -> None:
        self._bot = telegram.Bot(
            token=config.TELEGRAM_TOKEN,
            request=request,
        )
        self._lock = threading.RLock()
        self.default_reply_markup = default_reply_markup

    @synchronized
    def send_message(self, text: str, *, parse_mode: str = 'markdown', reply_markup=None) -> None:
        if not reply_markup and self.default_reply_markup:
            if callable(self.default_reply_markup):
                reply_markup = self.default_reply_markup()
            else:
                reply_markup = self.default_reply_markup

        try:
            self._bot.send_message(
                self.chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized
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

    @synchronized
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

    @synchronized
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

    @synchronized
    def error(self, text: str, *, _title: str = 'Error') -> None:
        logging.warning(text)
        self.send_message(f'{emojize(":pager:")} ️*{_title}* ```\n{text}\n```')

    @synchronized
    def exception(self, exp: Exception) -> None:
        self.error(f'{repr(exp)}\n{"".join(traceback.format_tb(exp.__traceback__))}', _title='Exception')

    @synchronized
    def start_typing(self):
        try:
            self._bot.send_chat_action(chat_id=self.chat_id, action=telegram.ChatAction.TYPING)
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)

    @synchronized
    def get_updates(self) -> typing.Iterator[Message]:
        now = datetime.datetime.now()

        try:
            updates = self._bot.get_updates(offset=self._updates_offset, timeout=5)
        except (TelegramNetworkError, TelegramTimedOut,) as e:
            logging.warning(e, exc_info=True)
            sleep(1)
            return

        if updates:
            self._updates_offset = updates[-1].update_id + 1

        for update in updates:
            if not update.message:
                continue

            if update.message.from_user.username != config.TELEGRAM_USERNAME:
                text = update.message.text.replace("`", "\\`")
                self.error(
                    f'User "{update.effective_user.name}" (@{update.effective_user.username}) sent '
                    f'in chat #{update.effective_chat.id}:\n'
                    f'```\n{text}\n```'
                )
                continue

            sent_at = update.message.date.astimezone(config.PY_TIME_ZONE).replace(tzinfo=None)

            if now - sent_at < datetime.timedelta(seconds=30):
                yield self._parse_update(update)
            else:
                logging.debug(f'Skip telegram message: {update.message.text}')

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
            text=text,
            command=Command(
                name=command_name,
                args=command_args,
                kwargs=command_kwargs,
            ),
        )
