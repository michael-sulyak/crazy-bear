import logging

from libs.messengers.base import MessageInfo
from libs.messengers.telegram import TelegramMessenger

from .... import config
from .. import events
from ..base import Command, Message


def process_telegram_message(message: MessageInfo, *, messanger: TelegramMessenger) -> None:
    authorized_user = bool(
        message.user.username
        and config.TELEGRAM_USERNAME
        and message.user.username.casefold() == config.TELEGRAM_USERNAME.lstrip('@').casefold()
    )

    authorized_chat = message.chat.id == config.TELEGRAM_CHAT_ID

    if not authorized_chat or not authorized_user:
        reasons = []

        if not authorized_user:
            reasons.append('username mismatch')

        if not authorized_chat:
            reasons.append('chat mismatch')

        text = ''.join(
            char if char.isprintable() else ascii(char)[1:-1]
            for char in message.text
        ).replace('`', '\\`')

        logging.warning(
            'Rejected Telegram command (%s; expected username=@%s, chat=%s). '
            'User %r (@%s, id=%s) sent in chat #%s:\n```\n%s\n```',
            ', '.join(reasons),
            config.TELEGRAM_USERNAME,
            config.TELEGRAM_CHAT_ID,
            message.user.name,
            message.user.username,
            message.user.id,
            message.chat.id,
            text,
        )
        return

    if not message.text.strip():
        return

    command = Command.from_string(message.text)
    command.callback_message_id = message.callback_message_id

    events.new_message.send(
        message=Message(
            username=message.user.username,
            chat_id=message.chat.id,
            text=message.text,
            command=command,
        ),
    )
