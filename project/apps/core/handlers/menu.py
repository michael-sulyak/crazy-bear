import typing

from ..base import BaseCommandHandler, Command
from ...messengers.constants import BotCommands
from ...messengers.utils import TelegramMenu


__all__ = (
    'Menu',
)


class Menu(BaseCommandHandler):
    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RETURN:
            menu = self.state[TelegramMenu.MENU]

            if len(menu) > 1:
                self.state[TelegramMenu.MENU] = menu[:-1]
                self.messenger.send_message('←')

            return True

        if command.name == BotCommands.OTHER:
            self.state[TelegramMenu.MENU].append(TelegramMenu.OTHER_MENU)
            self.messenger.send_message('→')

            return True

        return False
