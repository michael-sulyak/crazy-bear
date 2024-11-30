import logging

from libs.messengers.base import MessageInfo
from libs.messengers.telegram import TelegramMessenger

from .... import config
from .. import events
from ..base import Command, Message


def process_telegram_message(message: MessageInfo, *, messanger: TelegramMessenger) -> None:
    if message.user.username != config.TELEGRAM_USERNAME:
        text = message.text.replace('`', '\\`')

        error_message = (
            f'User "{message.user.name}" (@{message.user.username}) sent in chat #{message.chat.id}:\n```\n{text}\n```'
        )

        if text == '/start':
            # Don't need to log "/start", because a lot of users can try to run the bot.
            logging.warning(error_message)
        else:
            messanger.error(error_message)

        return

    events.new_message.send(
        message=Message(
            username=message.user.username,
            chat_id=message.chat.id,
            text=message.text,
            command=Command.from_string(message.text),
        )
    )
