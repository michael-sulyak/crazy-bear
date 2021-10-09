import typing

from telegram import ReplyKeyboardMarkup

from ..base import BaseModule, Command
from ..constants import (
    ARDUINO_IS_ENABLED, AUTO_SECURITY_IS_ENABLED, BotCommands, RECOMMENDATION_SYSTEM_IS_ENABLED, SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
)
from ...common.constants import AUTO, OFF, ON
from ...common.exceptions import Shutdown
from ...common.state import State


__all__ = (
    'Menu',
    'TelegramMenu',
)


class TelegramMenu:
    MENU = 'menu'
    MAIN_MENU = 'main_menu'
    OTHER_MENU = 'other_menu'

    state: State

    def __init__(self, state: State) -> None:
        self.state = state
        self.state.create(self.MENU, [self.MAIN_MENU])

    def __call__(self, *args, **kwargs) -> ReplyKeyboardMarkup:
        menu = self.state[self.MENU][-1]

        if menu == self.MAIN_MENU:
            return self._get_main_menu()
        elif menu == self.OTHER_MENU:
            return self._get_other_menu()

    def _get_main_menu(self) -> ReplyKeyboardMarkup:
        use_camera: bool = self.state[USE_CAMERA]

        first_line = [
            f'{BotCommands.SECURITY} {OFF if self.state[SECURITY_IS_ENABLED] else ON}',
            f'{BotCommands.SECURITY} {AUTO} {OFF if self.state[AUTO_SECURITY_IS_ENABLED] else ON}',
            f'{BotCommands.ARDUINO} {OFF if self.state[ARDUINO_IS_ENABLED] else ON}',
        ]

        second_line = [
            f'{BotCommands.CAMERA} {OFF if use_camera else ON}',
        ]

        if use_camera:
            second_line.append(f'{BotCommands.CAMERA} photo')
            second_line.append(f'{BotCommands.CAMERA} video {OFF if self.state[VIDEO_RECORDING_IS_ENABLED] else ON}')

        third_line = [
            BotCommands.STATUS,
            f'{BotCommands.STATS} -a -e -r',
            BotCommands.OTHER,
        ]

        return ReplyKeyboardMarkup([
            first_line,
            second_line,
            third_line,
        ])

    def _get_other_menu(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [BotCommands.DB_STATS, BotCommands.CHECK_DB, BotCommands.STATS],
            [
                f'{BotCommands.RECOMMENDATION_SYSTEM} {OFF if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] else ON}',
                BotCommands.RESTART,
            ],
            [BotCommands.REPORT, BotCommands.CONNECTED_DEVICES, BotCommands.RETURN],
        ])


class Menu(BaseModule):
    NEXT = '→'
    PREV = '←'

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RESTART:
            raise Shutdown

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
