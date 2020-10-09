import datetime
import typing

from .. import events
from ..base import BaseCommandHandler, Command
from ..constants import AUTO_SECURITY_IS_ENABLED, SECURITY_IS_ENABLED, USER_IS_CONNECTED_TO_ROUTER, USE_CAMERA
from ...common.constants import AUTO, OFF, ON
from ...messengers.constants import BotCommands


__all__ = (
    'AutoSecurity',
)


class AutoSecurity(BaseCommandHandler):
    initial_state = {
        AUTO_SECURITY_IS_ENABLED: False,
    }
    _last_movement_at: typing.Optional[datetime.datetime] = None
    _default_use_camera: typing.Optional[bool] = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        events.motion_detected.connect(self._motion_detected)

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.SECURITY:
            if command.first_arg == AUTO:
                if command.second_arg == ON:
                    self._enable_auto_security()
                elif command.second_arg == OFF:
                    self._disable_auto_security()
                else:
                    return False
            elif command.first_arg == ON:
                self.state[SECURITY_IS_ENABLED] = True
                self.messenger.send_message('Security is enabled')
            elif command.first_arg == OFF:
                self.state[SECURITY_IS_ENABLED] = False
                self.messenger.send_message('Security is disabled')
            else:
                return False

            return True

        return False

    def update(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        user_is_connected: bool = self.state[USER_IS_CONNECTED_TO_ROUTER]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if user_is_connected and security_is_enabled:
            self.messenger.send_message('The owner is found')
            self._run_command(BotCommands.SECURITY, OFF)

        if not user_is_connected and not security_is_enabled:
            self.messenger.send_message('The owner is not found')
            self._run_command(BotCommands.SECURITY, ON)

        now = datetime.datetime.now()
        use_camera: bool = self.state[USE_CAMERA]

        if not user_is_connected and self._last_movement_at and now - self._last_movement_at <= datetime.timedelta(
                minutes=30):
            if self._default_use_camera is None:
                self._default_use_camera = use_camera

            if not use_camera:
                self._run_command(BotCommands.CAMERA, ON)
        elif self._default_use_camera is not None and not self._default_use_camera and use_camera:
            self._run_command(BotCommands.CAMERA, OFF)

    def clear(self) -> None:
        self._disable_auto_security()

        events.motion_detected.disconnect(self._motion_detected)

    def _enable_auto_security(self):
        self.state[AUTO_SECURITY_IS_ENABLED] = True

        self.messenger.send_message('Auto security is enabled')

    def _disable_auto_security(self):
        use_camera: bool = self.state[USE_CAMERA]

        self.state[AUTO_SECURITY_IS_ENABLED] = False

        if self._default_use_camera is not None and not self._default_use_camera and use_camera:
            self._run_command(BotCommands.CAMERA, OFF)

        self._default_use_camera = None
        self._last_movement_at = None

        self.messenger.send_message('Auto security is disabled')

    def _motion_detected(self):
        self._last_movement_at = datetime.datetime.now()
