import requests
from telegram import ReplyKeyboardMarkup

from project import config
from .constants import BotCommands
from ..arduino.constants import ARDUINO_IS_ENABLED
from ..common.constants import OFF, ON
from ..common.state import State
from ..guard.constants import SECURITY_IS_ENABLED, USE_CAMERA


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL).json()


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
        use_camera, security_is_enabled, arduino_is_enabled = self.state.get_many(
            USE_CAMERA,
            SECURITY_IS_ENABLED,
            ARDUINO_IS_ENABLED,
        )

        first_line = [
            f'{BotCommands.SECURITY} {OFF if security_is_enabled else ON}',
            f'{BotCommands.ARDUINO} {OFF if arduino_is_enabled else ON}',
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

        return ReplyKeyboardMarkup((
            first_line,
            second_line,
            third_line,
        ))

    @staticmethod
    def _get_other_menu() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup((
            (BotCommands.REPORT, BotCommands.STOP),
            (BotCommands.RETURN,),
        ))
