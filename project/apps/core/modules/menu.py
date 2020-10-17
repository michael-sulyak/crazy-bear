import typing

from ..base import BaseModule, Command
from ...messengers.constants import BotCommands
from ...messengers.utils import TelegramMenu


__all__ = (
    'Menu',
)


class Menu(BaseModule):
    NEXT = '→'
    PREV = '←'

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RETURN:
            menu = self.state[TelegramMenu.MENU]

            if len(menu) > 1:
                self.state[TelegramMenu.MENU] = menu[:-1]
                self.messenger.send_message(self.PREV)

            return True

        if command.name == BotCommands.OTHER:
            self.state[TelegramMenu.MENU].append(TelegramMenu.OTHER_MENU)
            self.messenger.send_message(self.NEXT)

            return True

        return False
