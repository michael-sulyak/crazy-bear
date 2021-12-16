import os
import signal
import typing

from telegram import ReplyKeyboardMarkup

from ..base import BaseModule, Command
from ..constants import (
    ARDUINO_IS_ENABLED, AUTO_SECURITY_IS_ENABLED, BotCommands, RECOMMENDATION_SYSTEM_IS_ENABLED, SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
)
from ...common.constants import AUTO, OFF, ON
from ...common.state import State


__all__ = (
    'Menu',
    'TelegramMenu',
)


class TelegramMenu:
    MENU = 'menu'
    MAIN_MENU = 'main'
    OTHER_MENU = 'other'
    DEV_MENU = 'dev'

    menu_map: dict

    state: State

    def __init__(self, state: State) -> None:
        self.state = state
        self.state.create(self.MENU, [self.MAIN_MENU])

        self.menu_map = {
            self.MAIN_MENU: self._get_main_menu,
            self.OTHER_MENU: self._get_other_menu,
            self.DEV_MENU: self._get_dev_menu,
        }

    def __call__(self, *args, **kwargs) -> ReplyKeyboardMarkup:
        if not self.state[self.MENU]:
            return self._get_main_menu()

        menu = self.state[self.MENU][-1]

        if menu not in self.menu_map:
            return self._get_main_menu()

        return self.menu_map[menu]()

    def _get_main_menu(self) -> ReplyKeyboardMarkup:
        use_camera: bool = self.state[USE_CAMERA]

        first_line = (
            f'{BotCommands.SECURITY} {OFF if self.state[SECURITY_IS_ENABLED] else ON}',
            f'{BotCommands.SECURITY} {AUTO} {OFF if self.state[AUTO_SECURITY_IS_ENABLED] else ON}',
            f'{BotCommands.ARDUINO} {OFF if self.state[ARDUINO_IS_ENABLED] else ON}',
        )

        second_line = [
            f'{BotCommands.CAMERA} {OFF if use_camera else ON}',
        ]

        if use_camera:
            second_line.append(f'{BotCommands.CAMERA} photo')
            second_line.append(f'{BotCommands.CAMERA} record {OFF if self.state[VIDEO_RECORDING_IS_ENABLED] else ON}')

        third_line = (
            BotCommands.STATUS,
            f'{BotCommands.STATS} -s',
            f'{BotCommands.TO} {self.OTHER_MENU}',
        )

        return self._generate_reply_keyboard_markup('Main menu', (
            first_line,
            second_line,
            third_line,
        ))

    def _get_other_menu(self) -> ReplyKeyboardMarkup:
        return self._generate_reply_keyboard_markup('Other options', (
            (BotCommands.REPORT, BotCommands.STATS, BotCommands.HELP,),
            (f'{BotCommands.RECOMMENDATION_SYSTEM} {OFF if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] else ON}',),
            (f'{BotCommands.TO} {self.DEV_MENU}', BotCommands.RETURN,),
        ))

    def _get_dev_menu(self) -> ReplyKeyboardMarkup:
        return self._generate_reply_keyboard_markup('Dev menu', (
            (BotCommands.DB_STATS, BotCommands.CHECK_DB, BotCommands.RESTART),
            (BotCommands.CONNECTED_DEVICES, BotCommands.DEVICES,),
            (BotCommands.RETURN,),
        ))

    @staticmethod
    def _generate_reply_keyboard_markup(name: str, rows: typing.Sequence) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            rows,
            resize_keyboard=True,
            input_field_placeholder=f'{name}: Choose a command...',
        )


class Menu(BaseModule):
    NEXT = '→'
    PREV = '←'

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RESTART:
            os.kill(os.getpid(), signal.SIGTERM)
            return True

        if command.name == BotCommands.RETURN:
            menu = self.state[TelegramMenu.MENU]

            if len(menu) > 1:
                self.state[TelegramMenu.MENU] = menu[:-1]
                self.messenger.send_message(self.PREV)
            else:
                self.messenger.send_message('?')

            return True

        if command.name == BotCommands.TO:
            self.state[TelegramMenu.MENU].append(command.first_arg)
            self.messenger.send_message(self.NEXT)

            return True

        return False
