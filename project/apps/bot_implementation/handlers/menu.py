from .. import constants
from ..utils import TelegramMenu
from ...messengers.base import BaseBotCommandHandler, Command


__all__ = (
    'Menu',
)


class Menu(BaseBotCommandHandler):
    support_commands = {
        constants.BotCommands.RETURN,
        constants.BotCommands.STOP,
        constants.BotCommands.OTHER,
    }

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.RETURN:
            menu = self.state[TelegramMenu.MENU]

            if len(menu) > 1:
                self.state[TelegramMenu.MENU] = menu[:-1]
                self.messenger.send_message('<-')
        elif command.name == constants.BotCommands.OTHER:
            menu = self.state[TelegramMenu.MENU]
            menu.append(TelegramMenu.OTHER_MENU)
            self.state[TelegramMenu.MENU] = menu
            self.messenger.send_message('->')
        elif command.name == constants.BotCommands.STOP:
            # TODO: Implement
            pass
            # os.system('sudo poweroff')
            # raise KeyboardInterrupt
            # # exit(0)

