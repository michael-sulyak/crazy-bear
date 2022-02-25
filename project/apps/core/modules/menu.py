import abc
import os
import signal
import typing

from telegram import ReplyKeyboardMarkup

from .. import constants
from ..base import BaseModule, Command
from ...common.constants import AUTO, OFF, ON
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
                f'{constants.BotCommands.SECURITY} {OFF if self.state[constants.SECURITY_IS_ENABLED] else ON}',
                f'{constants.BotCommands.SECURITY} {AUTO} {OFF if self.state[constants.AUTO_SECURITY_IS_ENABLED] else ON}',
            ),
            (
                f'{constants.BotCommands.TO} {AllFuncsPage.code}',
                f'{constants.BotCommands.TO} {LampPage.code}',
            ),
            (
                constants.BotCommands.STATUS,
                f'{constants.BotCommands.STATS} -s',
            ),
        )


class LampPage(BasePage):
    name = 'Lamp menu'
    code = 'lamp'

    def _get_items(self) -> typing.Sequence:
        return (
            (
                f'{constants.BotCommands.LAMP} {OFF if self.state[constants.MAIN_LAMP_IS_ON] else ON}',
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
                f'{constants.BotCommands.LAMP} increase_brightness',
                f'{constants.BotCommands.LAMP} decrease_brightness',
            ),
            # (
            #     f'{BotCommands.LAMP} increase_color_temp',
            #     f'{BotCommands.LAMP} decrease_color_temp',
            # ),
            (
                f'{constants.BotCommands.LAMP} color_temp 150',
                f'{constants.BotCommands.LAMP} color_temp 250',
            ),
            (
                f'{constants.BotCommands.LAMP} color_temp 350',
                f'{constants.BotCommands.LAMP} color_temp 500',
            ),
            (
                constants.BotCommands.RETURN,
            ),
        )


class AllFuncsPage(BasePage):
    name = 'All functions'
    code = 'all_funcs'

    def _get_items(self) -> typing.Sequence:
        use_camera: bool = self.state[constants.USE_CAMERA]

        camera_line = [
            f'{constants.BotCommands.CAMERA} {OFF if use_camera else ON}',
        ]

        if use_camera:
            camera_line.append(f'{constants.BotCommands.CAMERA} photo')
            camera_line.append(
                f'{constants.BotCommands.CAMERA} record {OFF if self.state[constants.VIDEO_RECORDING_IS_ENABLED] else ON}')

        return (
            camera_line,
            (
                f'{constants.BotCommands.RECOMMENDATION_SYSTEM}'
                f' {OFF if self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED] else ON}',
            ),
            (f'{constants.BotCommands.ARDUINO} {OFF if self.state[constants.ARDUINO_IS_ENABLED] else ON}',),
            (constants.BotCommands.STATS, constants.BotCommands.DB_STATS, constants.BotCommands.CHECK_DB,),
            (constants.BotCommands.RAW_WIFI_DEVICES, constants.BotCommands.WIFI_DEVICES,),
            (constants.BotCommands.RESTART,),
            (constants.BotCommands.HELP, constants.BotCommands.RETURN,),
        )


class Menu(BaseModule):
    NEXT = '→'
    PREV = '←'

    def process_command(self, command: Command) -> typing.Any:
        if command.name == constants.BotCommands.RESTART:
            os.kill(os.getpid(), signal.SIGTERM)
            return True

        if command.name == constants.BotCommands.RETURN:
            menu = self.state[TelegramMenu.menu_state_name]

            if len(menu) > 1:
                self.state[TelegramMenu.menu_state_name] = menu[:-1]
                self.messenger.send_message(self.PREV)
            else:
                self.messenger.send_message('?')

            return True

        if command.name == constants.BotCommands.TO:
            with self.state.lock(TelegramMenu.menu_state_name):
                self.state[TelegramMenu.menu_state_name].append(command.first_arg)

            self.messenger.send_message(self.NEXT)

            return True

        return False
