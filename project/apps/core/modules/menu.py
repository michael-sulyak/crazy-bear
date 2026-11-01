import abc
import contextlib
import logging
from collections import OrderedDict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest

from libs.messengers.utils import escape_markdown

from ...common import interface
from ...common.state import State
from ...common.utils import is_heating_season
from .. import constants, events
from ..base import BaseModule, Command
from ..constants import BotCommands, PrettyBotCommands as Buttons
from ..telegram_ui import BUTTON_CALLBACKS, PANEL_ACTIONS


__all__ = (
    'Menu',
    'TelegramMenu',
)


class TelegramMenu:
    def __init__(self, state: State | None = None) -> None:
        pass

    def __call__(self, *args, **kwargs) -> ReplyKeyboardMarkup:
        first_row = [Buttons.SECURITY, Buttons.LAMP]

        if is_heating_season():
            first_row.append(Buttons.HEATING)

        return ReplyKeyboardMarkup(
            keyboard=[
                first_row,
                [Buttons.STATUS, Buttons.ALL_FUNCS],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder='Open a section or type /help',
        )


class BasePage(abc.ABC):
    name: str
    code: str
    parent: str | None = None
    description = 'Choose an action below\\.'

    def __init__(self, *, state: State) -> None:
        self.state = state

    def get(self) -> InlineKeyboardMarkup:
        rows = [
            [InlineKeyboardButton(item, callback_data=BUTTON_CALLBACKS[item]) for item in row]
            for row in self._get_items()
        ]

        navigation = [InlineKeyboardButton('🔄 Refresh', callback_data=f'ui:{self.code}')]

        if self.parent is not None:
            navigation.insert(0, InlineKeyboardButton(Buttons.BACK, callback_data=f'ui:{self.parent}'))

        rows.append(navigation)

        return InlineKeyboardMarkup(rows)

    def get_text(self) -> str:
        return f'*{self.name}*\n\n{self.description}'

    def _is_on(self, name: str) -> bool:
        return self.state.has(name) and bool(self.state[name])

    def _status(self, name: str) -> str:
        if not self.state.has(name) or self.state[name] is None:
            return 'Unknown'

        return 'On' if self.state[name] else 'Off'

    @abc.abstractmethod
    def _get_items(self) -> list[list[str]]:
        pass


class SecurityPage(BasePage):
    name = '🛡️ Security'
    code = 'security'

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.SECURITY_OFF if self._is_on(constants.SECURITY_IS_ENABLED) else Buttons.SECURITY_ON],
            [Buttons.SECURITY_AUTO_OFF if self._is_on(constants.AUTO_SECURITY_IS_ENABLED) else Buttons.SECURITY_AUTO_ON],
        ]

    def get_text(self) -> str:
        details = (
            f'Security: `{self._status(constants.SECURITY_IS_ENABLED)}`\n'
            f'Auto security: `{self._status(constants.AUTO_SECURITY_IS_ENABLED)}`\n\n'
            '*Auto security* follows whether you are at home\\. '
            'It can change security again after a manual action\\.'
        )
        return f'*{self.name}*\n\n{details}'


class LampPage(BasePage):
    name = '💡 Lamp'
    code = 'lamp'

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.LAMP_OFF if self._is_on(constants.MAIN_LAMP_IS_ON) else Buttons.LAMP_ON, Buttons.LAMP_DIM],
            [Buttons.LAMP_DIMMER, Buttons.LAMP_BRIGHTER],
            [Buttons.LAMP_COLORS],
        ]

    def get_text(self) -> str:
        details = (
            '*Night light* turns the lamp on very dimly\\.\n'
            'Adjust brightness here, or open *Colors* for white tones and colors\\.'
        )
        return f'*{self.name}* · `{self._status(constants.MAIN_LAMP_IS_ON)}`\n\n{details}'


class LampColorsPage(BasePage):
    name = '🎨 Lamp · Colors'
    code = 'lamp_colors'
    parent = 'lamp'
    description = (
        'Choose a *white\\-light tone* or a *color*\\. These adjust the current lamp settings\\.'
    )

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.LAMP_WARM, Buttons.LAMP_COOL],
            [Buttons.LAMP_WHITE, Buttons.LAMP_YELLOW],
            [Buttons.LAMP_BLUE, Buttons.LAMP_GREEN],
        ]


class HistoryPage(BasePage):
    name = '📊 History'
    code = 'history'
    description = (
        'Choose a period for home and WiFi charts\\.\n'
        '*Full history* includes system diagnostics for the last `24 h`\\.\n\n'
        'Custom period: `/stats 12 hours -s`'
    )

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.HISTORY_1, Buttons.HISTORY_6],
            [Buttons.HISTORY_24, Buttons.HISTORY_7D],
            [Buttons.STATS],
        ]


class HeatingPage(BasePage):
    name = '🌡️ Heating'
    code = 'heating'
    description = (
        '*Pause* all radiator valves or *boost* heating to *30 °C*\\.\n'
        'The controller requests the weekly schedule again when the timer expires\\.\n'
        '_It must remain online to end a boost on time\\._\n'
        'A new pause or boost *replaces the previous override* and starts from now\\.\n\n'
        'Custom duration in hours: `/trv disable 1.5` or `/trv boost 0.5`'
    )

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.HEATING_RESUME],
            [Buttons.HEATING_PAUSE_2, Buttons.HEATING_PAUSE_4],
            [Buttons.HEATING_BOOST_2, Buttons.HEATING_BOOST_4],
        ]

    def get_text(self) -> str:
        if not self.state.has(constants.HEATING_PAUSED_UNTIL):
            mode = 'Controller state: `Unknown`'
        elif (deadline := self.state[constants.HEATING_PAUSED_UNTIL]) is not None:
            mode = f'*Pause* requested until `{deadline:%d.%m.%Y, %H:%M:%S}`'
        elif (
            self.state.has(constants.HEATING_BOOSTED_UNTIL)
            and (deadline := self.state[constants.HEATING_BOOSTED_UNTIL]) is not None
        ):
            mode = f'*30 °C boost* requested until `{deadline:%d.%m.%Y, %H:%M:%S}`'
        else:
            mode = '`Schedule requested`'

        return f'*{self.name}*\n\n{mode}\n\n{self.description}'


class CameraPage(BasePage):
    name = '📷 Camera'
    code = 'camera'
    parent = 'all_funcs'

    def _get_items(self) -> list[list[str]]:
        if self._is_on(constants.USE_CAMERA):
            return [
                [Buttons.CAMERA_PHOTO],
                [
                    Buttons.CAMERA_RECORD_OFF
                    if self._is_on(constants.VIDEO_RECORDING_IS_ENABLED)
                    else Buttons.CAMERA_RECORD_ON,
                ],
                [Buttons.CAMERA_OFF],
            ]
        if self._is_on(constants.CAMERA_IS_AVAILABLE):
            return [[Buttons.CAMERA_ON]]
        return [[Buttons.STATUS]]

    def get_text(self) -> str:
        if not self._is_on(constants.CAMERA_IS_AVAILABLE) and not self._is_on(constants.USE_CAMERA):
            details = 'No camera is currently available\\. Connect a camera before enabling it\\.'
        else:
            details = (
                f'Camera: `{self._status(constants.USE_CAMERA)}`\n'
                f'Recording: `{self._status(constants.VIDEO_RECORDING_IS_ENABLED)}`\n\n'
                '*Enable the camera* to take a photo\\. *Stop recording* to receive the video\\.'
            )
        return f'*{self.name}*\n\n{details}'


class AllFuncsPage(BasePage):
    name = '🧰 More'
    code = 'all_funcs'
    description = '*History*, optional *Camera* controls, *Help*, and *System* tools\\.'

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.CAMERA],
            [Buttons.SYSTEM, Buttons.HISTORY],
            [Buttons.HELP, Buttons.ALL_COMMANDS],
        ]


class SystemPage(BasePage):
    name = '⚙️ System'
    code = 'system'
    parent = 'all_funcs'
    description = 'Inspect *WiFi* and *database usage*\\.'

    def _get_items(self) -> list[list[str]]:
        return [
            [Buttons.WIFI, Buttons.DB_STATS],
        ]


PAGE_CLASSES = (
    AllFuncsPage,
    SecurityPage,
    LampPage,
    LampColorsPage,
    HistoryPage,
    HeatingPage,
    CameraPage,
    SystemPage,
)
PAGES_MAP = {page.code: page for page in PAGE_CLASSES}


@interface.module(
    title='Menu',
    description='Navigate home controls and system tools.',
)
class Menu(BaseModule):
    max_panels = 128

    def __init__(self, *, context) -> None:
        self._panels: OrderedDict[int, str] = OrderedDict()
        self._last_page = 'all_funcs'
        super().__init__(context=context)

    def process_command(self, command: Command) -> bool:
        if command.callback_message_id is not None and command.name == BotCommands.STATUS:
            self._panels.pop(command.callback_message_id, None)

        return super().process_command(command)

    def _show_page(self, page_code: str, *, message_id: int | None = None, feedback: str = '') -> None:
        self.messenger.ensure_navigation()
        page = PAGES_MAP[page_code](state=self.state)
        text = page.get_text()

        if feedback:
            text += f'\n\n{escape_markdown(feedback)}'

        markup = page.get()

        if message_id is not None and self._panels.get(message_id) != page_code:
            # Fail closed if Telegram applies navigation but the response is lost.
            self._panels.pop(message_id, None)

        try:
            sent_id = self.messenger.send_message(
                text, use_markdown=True, reply_markup=markup, message_id=message_id,
            )
        except BadRequest as exc:
            if message_id is None or str(exc).casefold() not in {
                "message can't be edited", 'message to edit not found',
            }:
                raise

            # Replace only the view, never repeat the device command.
            self._panels.pop(message_id, None)
            sent_id = self.messenger.send_message(text, use_markdown=True, reply_markup=markup)

        if isinstance(sent_id, int):
            self._panels[sent_id] = page_code
            self._panels.move_to_end(sent_id)

            while len(self._panels) > self.max_panels:
                self._panels.popitem(last=False)

        self._last_page = page_code

    @interface.command(BotCommands.RETURN)
    def _return(self) -> None:
        parent = PAGES_MAP[self._last_page].parent
        self._show_page(parent or 'all_funcs')

    @interface.command(BotCommands.TO, interface.Value('name'))
    def _to(self, command: Command) -> None:
        name = command.first_arg

        if name == 'main':
            # Compatibility for old links; no separate home page remains.
            self._run_command(BotCommands.STATUS)
            return

        if name not in PAGES_MAP:
            self.messenger.send_message('Unknown section. Use /status or the navigation keyboard.')
            return

        self._show_page(
            name,
            message_id=command.callback_message_id,
        )

    @interface.command('/panel', interface.Value('action'))
    def _action(self, command: Command) -> None:
        action = command.first_arg
        message_id = command.callback_message_id

        if command.kwargs or len(command.args) != 1:
            self.messenger.send_message('Invalid panel action. Open the section again from the keyboard.')
            return

        entry = PANEL_ACTIONS.get(action)

        if entry is None or message_id is None or self._panels.get(message_id) != entry[0]:
            self.messenger.send_message('This panel is no longer active. Open the section again from the keyboard.')
            return

        page_code, text = entry
        # Capture only synchronous text feedback from this action's thread.
        # Media, background alerts, and normal typed commands are unaffected.
        capture = (
            self.messenger.capture_feedback()
            if page_code in {'lamp', 'lamp_colors', 'security', 'heating', 'camera'}
            else contextlib.nullcontext([])
        )

        with capture as feedback:
            results, exceptions = events.input_command.process(command=Command.from_string(text))

        if exceptions:
            for exception in exceptions:
                logging.error(
                    'Inline panel action failed: %s', action,
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

            feedback.append('⚠️ Action failed or was only partly applied. Refresh and check before trying again.')
        elif not any(result is True for result in results):
            feedback.append('⚠️ This action is not available.')
        elif not feedback:
            feedback.append('Request processed. Additional data will be sent separately when available.')

        if feedback:
            feedback = ['☑️ Result:', *feedback]

        summary = '\n'.join(feedback)
        self._show_page(page_code, message_id=message_id, feedback=summary)
