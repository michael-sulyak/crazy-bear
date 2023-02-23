from libs.messengers.base import MessageInfo
from libs.messengers.telegram import TelegramMessenger
from .. import events
from ..base import Message, Command
from .... import config


def process_telegram_message(message: MessageInfo, *, messanger: TelegramMessenger) -> None:
    if message.user.username != config.TELEGRAM_USERNAME:
        text = message.text.replace("`", "\\`")

        messanger.error(
            f'User "{message.user.name}" '
            f'(@{message.user.username}) sent '
            f'in chat #{message.chat.id}:\n'
            f'```\n{text}\n```'
        )

        return

    events.new_message.send(message=Message(
        username=message.user.username,
        chat_id=message.chat.id,
        text=message.text,
        command=Command.from_string(message.text),
    ))
