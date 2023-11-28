import abc
import typing

from emoji.core import emojize
from telegram import ReplyKeyboardMarkup, KeyboardButton

from .. import constants
from ..base import BaseModule, Command
from ...common import interface
from ...common.constants import OFF, ON
from ...common.state import State


__all__ = (
    'Menu',
    'TelegramMenu',
)


class TelegramMenu:
    menu_state_name = 'menu'
    home_page_code: str
    state: State
    _last_result: typing.Optional[typing.Sequence] = None

    def __init__(self, state: State) -> None:
        self.state = state
        self.home_page_code = MainPage.code
        self.state.create(self.menu_state_name, [self.home_page_code])

        pages = (
            MainPage,
            AllFuncsPage,
            LampPage,
        )

        self.pages_map = {
            page.code: page(state=state)
            for page in pages
        }

    def __call__(self, *args, **kwargs) -> typing.Optional[ReplyKeyboardMarkup]:
        with self.state.lock(self.menu_state_name):
            if not self.state[self.menu_state_name]:
                page_code = self.home_page_code
            else:
                page_code = self.state[self.menu_state_name][-1]

                if page_code not in self.pages_map:
                    page_code = self.home_page_code

            result = self.pages_map[page_code].get()

            if result == self._last_result:
                return None

            self._last_result = result

            return result


class BasePage(abc.ABC):
    name: str
    code: str
    state: State

    def __init__(self, *, state: State) -> None:
        self.state = state

    def get(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=self._get_items(),
            resize_keyboard=True,
            input_field_placeholder=f'{self.name}: Choose a command...',
        )

    @abc.abstractmethod
    def _get_items(self) -> list[list]:
        pass


class MainPage(BasePage):
    name = 'Main menu'
    code = 'main'

    def _get_items(self) -> list[list[KeyboardButton]]:
        return [
            [
                KeyboardButton(text=constants.PrettyBotCommands.SECURITY_OFF)
                if self.state[constants.SECURITY_IS_ENABLED] else
                KeyboardButton(text=constants.PrettyBotCommands.SECURITY_ON),

                KeyboardButton(text=constants.PrettyBotCommands.SECURITY_AUTO_OFF)
                if self.state[constants.AUTO_SECURITY_IS_ENABLED] else
                KeyboardButton(text=constants.PrettyBotCommands.SECURITY_AUTO_ON),
            ],
            [
                KeyboardButton(text=constants.PrettyBotCommands.ALL_FUNCS),
                KeyboardButton(text=constants.PrettyBotCommands.LAMP),
            ],
            [
                KeyboardButton(text=constants.PrettyBotCommands.STATUS),
                KeyboardButton(text=constants.PrettyBotCommands.SHORT_STATS),
            ],
        ]


class LampPage(BasePage):
    name = 'Lamp menu'
    code = 'lamp'

    def _get_items(self) -> list[list[KeyboardButton]]:
        main_lamp_is_on = self.state[constants.MAIN_LAMP_IS_ON]

        first_row = [
            KeyboardButton(text=f'{constants.BotCommands.LAMP} {OFF if main_lamp_is_on else ON}')
        ]

        if not main_lamp_is_on:
            first_row.append(
                KeyboardButton(text=f'{constants.BotCommands.LAMP} {ON} 5'),
            )

        return [
            first_row,
            [
                KeyboardButton(text=f'{constants.BotCommands.LAMP} increase_brightness'),
                KeyboardButton(text=f'{constants.BotCommands.LAMP} decrease_brightness'),
            ],
            [
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color_temp 150'),
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color_temp 250'),
            ],
            [
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color_temp 350'),
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color_temp 500'),
            ],
            [
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color white'),
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color yellow'),
            ],
            [
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color blue'),
                KeyboardButton(text=f'{constants.BotCommands.LAMP} color green'),
            ],
            [
                KeyboardButton(text=constants.BotCommands.RETURN),
            ],
        ]


class AllFuncsPage(BasePage):
    name = 'All functions'
    code = 'all_funcs'

    def _get_items(self) -> list[list[KeyboardButton]]:
        use_camera: bool = self.state[constants.USE_CAMERA]

        camera_line = [
            KeyboardButton(text=f'{constants.BotCommands.CAMERA} {OFF if use_camera else ON}'),
        ]

        if use_camera:
            camera_line.append(KeyboardButton(text=f'{constants.BotCommands.CAMERA} photo'))
            camera_line.append(
                KeyboardButton(
                    text=f'{constants.BotCommands.CAMERA} record {OFF if self.state[constants.VIDEO_RECORDING_IS_ENABLED] else ON}'),
            )

        return [
            camera_line,
            [
                KeyboardButton(
                    f'{constants.BotCommands.ARDUINO} {OFF if self.state[constants.ARDUINO_IS_ENABLED] else ON}',
                ),
            ],
            [
                KeyboardButton(constants.BotCommands.STATS),
                KeyboardButton(constants.BotCommands.DB_STATS),
                KeyboardButton(constants.BotCommands.COMPRESS_DB),
            ],
            [
                KeyboardButton(constants.BotCommands.RAW_WIFI_DEVICES),
                KeyboardButton(constants.BotCommands.WIFI_DEVICES)
            ],
            [
                KeyboardButton(constants.BotCommands.HELP),
                KeyboardButton(constants.BotCommands.RETURN)
            ],
        ]


@interface.module(
    title='Menu',
    description=(
        'The module provides the menu.'
    ),
)
class Menu(BaseModule):
    NEXT = emojize(':right_arrow:')
    PREV = emojize(':BACK_arrow:')

    def process_command(self, command: Command) -> typing.Any:
        if command.name == constants.BotCommands.RETURN:
            self._return()
            return True

        if command.name == constants.BotCommands.TO:
            self._to(command.first_arg)
            return True

        return False

    @interface.command(constants.BotCommands.RETURN)
    def _return(self) -> None:
        menu = self.state[TelegramMenu.menu_state_name]

        if len(menu) > 1:
            self.state[TelegramMenu.menu_state_name] = menu[:-1]
            state_name = self.state[TelegramMenu.menu_state_name][-1]
            self.messenger.send_message(f'{self.PREV} {state_name.replace("_", " ").capitalize()}')
        else:
            self.messenger.send_message(emojize(':thinking_face:'))

    @interface.command(constants.BotCommands.TO, interface.Value('name'))
    def _to(self, name: str) -> None:
        with self.state.lock(TelegramMenu.menu_state_name):
            self.state[TelegramMenu.menu_state_name].append(name)

        self.messenger.send_message(f'{self.NEXT} {name.replace("_", " ").capitalize()}')
