import logging
import traceback
import typing
from datetime import datetime, timedelta

import telegram
from emoji import emojize
from telegram.utils.request import Request as TelegramRequest

from .base import BaseMessenger, MessengerCommand, MessengerUpdate
from .mixins import CVMixin
from ... import config


class TelegramMessenger(CVMixin, BaseMessenger):
    chat_id: int = config.TELEGRAM_CHAT_ID
    default_reply_markup: typing.Optional
    _bot: telegram.Bot
    _updates_offset: typing.Optional[int] = None

    def __init__(self,
                 request: typing.Optional[TelegramRequest] = None,
                 default_reply_markup: typing.Optional = None) -> None:
        self._bot = telegram.Bot(
            token=config.TELEGRAM_TOKEN,
            request=request,
        )

        self.default_reply_markup = default_reply_markup

    def send_message(self, text: str, *, parse_mode: str = 'markdown', reply_markup=None) -> None:
        if not reply_markup and self.default_reply_markup:
            if callable(self.default_reply_markup):
                reply_markup = self.default_reply_markup()
            else:
                reply_markup = self.default_reply_markup

        self._bot.send_message(
            self.chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    def send_image(self, photo: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        self._bot.send_photo(
            self.chat_id,
            photo=photo,
            caption=caption,
        )

    def error(self, text: str, *, _title: str = 'Error') -> None:
        logging.warning(text)
        self.send_message(f'{emojize(":pager:")} ️*{_title}* ```\n{text}\n```')

    def exception(self, exp: Exception) -> None:
        self.error(f'{repr(exp)}\n{"".join(traceback.format_tb(exp.__traceback__))}', _title='Exception')

    def start_typing(self):
        try:
            self._bot.send_chat_action(chat_id=self.chat_id, action=telegram.ChatAction.TYPING)
        except telegram.error.TimedOut as e:
            logging.warning(e, exc_info=True)

    def get_updates(self) -> typing.Iterator:
        now = datetime.now()

        try:
            updates = self._bot.get_updates(offset=self._updates_offset, timeout=5)
        except telegram.error.TimedOut:
            return

        if updates:
            self._updates_offset = updates[-1].update_id + 1

        for update in updates:
            # TODO: Add logging

            if not update.message:
                continue

            if update.message.from_user.username != config.TELEGRAM_USERNAME:
                text = update.message.text.replace("`", "\\`")
                self.error(
                    f'User *{update.message.from_user.name}* sent:\n'
                    f'```\n{text}\n```'
                )
                continue

            sent_at = update.message.date.astimezone(config.PY_TIME_ZONE).replace(tzinfo=None)

            if now - sent_at < timedelta(seconds=30):
                yield self._parse_update(update)
            else:
                logging.debug(f'Skip telegram message: {update.message.text}')

    def _parse_update(self, update) -> MessengerUpdate:
        text: str = update.message.text

        params = text.split(' ')
        command_name = params[0]
        command_params = tuple(param.strip() for param in params[1:] if param)

        return MessengerUpdate(
            messenger=self,
            text=text,
            command=MessengerCommand(
                name=command_name,
                args=command_params,
                kwargs={},  # TODO: Implement
            ),
        )
