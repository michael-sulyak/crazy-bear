from telegram import ReplyKeyboardMarkup

from ..arduino.constants import ARDUINO_IS_ENABLED
from ..common.state import State
from ..guard.constants import SECURITY_IS_ENABLED, USE_CAMERA


class BotCommands:
    INIT = '/init'
    REPORT = '/report'

    TAKE_PICTURE = '/take_picture'

    SECURITY = '/security'
    ARDUINO = '/arduino'
    CAMERA = '/camera'

    STATUS = '/status'
    STATS = '/stats'

    GOOD_NIGHT = '/good_night'

    OTHER = '/other'
    STOP = '/stop'
    RETURN = '/return'


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
            f'{BotCommands.SECURITY} {"off" if security_is_enabled else "on"}',
            f'{BotCommands.ARDUINO} {"off" if arduino_is_enabled else "on"}',
        ]

        second_line = [
            f'{BotCommands.CAMERA} {"off" if use_camera else "on"}',
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


CPU_TEMPERATURE = 'cpu_temperature'