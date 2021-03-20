from telegram import ReplyKeyboardMarkup

from .constants import BotCommands
from ..common.constants import AUTO, OFF, ON
from ..common.state import State
from ..core.constants import (
    ARDUINO_IS_ENABLED, AUTO_SECURITY_IS_ENABLED, RECOMMENDATION_SYSTEM_IS_ENABLED,
    SECURITY_IS_ENABLED, USE_CAMERA,
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

        third_line = [
            BotCommands.STATUS,
            BotCommands.STATS,
            BotCommands.OTHER,
        ]

        return ReplyKeyboardMarkup([
            first_line,
            second_line,
            third_line,
        ])

    def _get_other_menu(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [BotCommands.REPORT, BotCommands.CONNECTED_DEVICES, BotCommands.DB_STATS],
            [f'{BotCommands.RECOMMENDATION_SYSTEM} {OFF if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] else ON}'],
            [BotCommands.RETURN],
        ])
