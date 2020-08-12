from .. import constants
from ..utils import TelegramMenu
from ...messengers.base import BaseCommandHandler, Command


__all__ = (
    'Menu',
)


class Menu(BaseCommandHandler):
    support_commands = {
        constants.BotCommands.RETURN,
        constants.BotCommands.OTHER,
    }

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.RETURN:
            menu = self.state[TelegramMenu.MENU]

            if len(menu) > 1:
                self.state[TelegramMenu.MENU] = menu[:-1]
                self.messenger.send_message('←')
        elif command.name == constants.BotCommands.OTHER:
            self.state[TelegramMenu.MENU].append(TelegramMenu.OTHER_MENU)
            self.messenger.send_message('→')
