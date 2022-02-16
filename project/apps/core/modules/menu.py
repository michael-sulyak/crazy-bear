import abc
import os
import signal
import typing

from telegram import ReplyKeyboardMarkup

from ..base import BaseModule, Command
from ..constants import (
    ARDUINO_IS_ENABLED, AUTO_SECURITY_IS_ENABLED, BotCommands, MAIN_LAMP_IS_ON, RECOMMENDATION_SYSTEM_IS_ENABLED,
    SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
)
from ...common.constants import AUTO, OFF, ON
from ...common.state import State


__all__ = (
    'MenuModule',
    'TelegramMenu',
)


class TelegramMenu:
    menu_state_name = 'menu'
    home_page_code: str
    pages_map: dict
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
            self._get_items(),
            resize_keyboard=True,
            input_field_placeholder=f'{self.name}: Choose a command...',
        )

    @abc.abstractmethod
    def _get_items(self) -> typing.Sequence:
        pass


class MainPage(BasePage):
    name = 'Main menu'
    code = 'main'

    def _get_items(self) -> typing.Sequence:
        return (
            (
                f'{BotCommands.SECURITY} {OFF if self.state[SECURITY_IS_ENABLED] else ON}',
                f'{BotCommands.SECURITY} {AUTO} {OFF if self.state[AUTO_SECURITY_IS_ENABLED] else ON}',
            ),
            (
                f'{BotCommands.TO} {AllFuncsPage.code}',
                f'{BotCommands.TO} {LampPage.code}',
            ),
            (
                BotCommands.STATUS,
                f'{BotCommands.STATS} -s',
            ),
        )


class LampPage(BasePage):
    name = 'Lamp menu'
    code = 'lamp'

    def _get_items(self) -> typing.Sequence:
        return (
            (
                f'{BotCommands.LAMP} {OFF if self.state[MAIN_LAMP_IS_ON] else ON}',
            ),
            # (
            #     f'{BotCommands.LAMP} color white',
            #     f'{BotCommands.LAMP} color yellow',
            # ),
            # (
            #     f'{BotCommands.LAMP} color blue',
            #     f'{BotCommands.LAMP} color green',
            # ),
            (
                f'{BotCommands.LAMP} increase_brightness',
                f'{BotCommands.LAMP} decrease_brightness',
            ),
            # (
            #     f'{BotCommands.LAMP} increase_color_temp',
            #     f'{BotCommands.LAMP} decrease_color_temp',
            # ),
            (
                f'{BotCommands.LAMP} color_temp 150',
                f'{BotCommands.LAMP} color_temp 250',
            ),
            (
                f'{BotCommands.LAMP} color_temp 350',
                f'{BotCommands.LAMP} color_temp 500',
            ),
            (
                BotCommands.RETURN,
            ),
        )


class AllFuncsPage(BasePage):
    name = 'All functions'
    code = 'all_funcs'

    def _get_items(self) -> typing.Sequence:
        use_camera: bool = self.state[USE_CAMERA]

        camera_line = [
            f'{BotCommands.CAMERA} {OFF if use_camera else ON}',
        ]

        if use_camera:
            camera_line.append(f'{BotCommands.CAMERA} photo')
            camera_line.append(f'{BotCommands.CAMERA} record {OFF if self.state[VIDEO_RECORDING_IS_ENABLED] else ON}')

        return (
            camera_line,
            (f'{BotCommands.RECOMMENDATION_SYSTEM} {OFF if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] else ON}',),
            (f'{BotCommands.ARDUINO} {OFF if self.state[ARDUINO_IS_ENABLED] else ON}',),
            (BotCommands.STATS, BotCommands.DB_STATS, BotCommands.CHECK_DB,),
            (BotCommands.RAW_WIFI_DEVICES, BotCommands.WIFI_DEVICES,),
            (BotCommands.RESTART,),
            (BotCommands.HELP, BotCommands.RETURN,),
        )


class MenuModule(BaseModule):
    NEXT = '→'
    PREV = '←'

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RESTART:
            os.kill(os.getpid(), signal.SIGTERM)
            return True

        if command.name == BotCommands.RETURN:
            menu = self.state[TelegramMenu.menu_state_name]

            if len(menu) > 1:
                self.state[TelegramMenu.menu_state_name] = menu[:-1]
                self.messenger.send_message(self.PREV)
            else:
                self.messenger.send_message('?')

            return True

        if command.name == BotCommands.TO:
            self.state[TelegramMenu.menu_state_name].append(command.first_arg)
            self.messenger.send_message(self.NEXT)

            return True

        return False
