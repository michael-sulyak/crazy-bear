import datetime
import threading
import typing

from .. import events
from ..base import BaseModule, Command
from ..constants import AUTO_SECURITY_IS_ENABLED, SECURITY_IS_ENABLED, USER_IS_CONNECTED_TO_ROUTER, USE_CAMERA
from ...common.constants import AUTO, OFF, ON
from ...common.utils import single_synchronized, synchronized
from ...messengers.constants import BotCommands


__all__ = (
    'AutoSecurity',
)


class AutoSecurity(BaseModule):
    initial_state = {
        AUTO_SECURITY_IS_ENABLED: False,
    }
    _last_movement_at: typing.Optional[datetime.datetime] = None
    _camera_was_not_used: bool = False
    _thirty_minutes: datetime.timedelta = datetime.timedelta(minutes=30)
    _lock_for_last_movement_at: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock_for_last_movement_at = threading.RLock()

    def connect_to_events(self) -> None:
        super().connect_to_events()
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

    def tick(self) -> None:
        if self.state[AUTO_SECURITY_IS_ENABLED]:
            self.task_queue.push(self._check_auto_security_status)

    @synchronized
    def disconnect(self) -> None:
        super().disconnect()
        self._disable_auto_security()
        events.motion_detected.disconnect(self._motion_detected)

    @synchronized
    def _enable_security(self) -> None:
        self.state[SECURITY_IS_ENABLED] = True
        self.messenger.send_message('Security is enabled')

    @synchronized
    def _disable_security(self) -> None:
        self.state[SECURITY_IS_ENABLED] = False
        self.messenger.send_message('Security is disabled')

    @synchronized
    def _enable_auto_security(self) -> None:
        self.state[AUTO_SECURITY_IS_ENABLED] = True
        self.messenger.send_message('Auto security is enabled')

    @synchronized
    def _disable_auto_security(self) -> None:
        use_camera: bool = self.state[USE_CAMERA]

        self.state[AUTO_SECURITY_IS_ENABLED] = False

        if self._camera_was_not_used and use_camera:
            self._run_command(BotCommands.CAMERA, OFF)

        self._camera_was_not_used = False

        self.messenger.send_message('Auto security is disabled')

    def _motion_detected(self) -> None:
        with self._lock_for_last_movement_at:
            self._last_movement_at = datetime.datetime.now()

    @single_synchronized
    def _check_auto_security_status(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        user_is_connected: bool = self.state[USER_IS_CONNECTED_TO_ROUTER]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if user_is_connected and security_is_enabled:
            self.messenger.send_message('The owner is found')
            self._run_command(BotCommands.SECURITY, OFF)
            return

        if not user_is_connected and not security_is_enabled:
            self.messenger.send_message('The owner is not found')
            self._run_command(BotCommands.SECURITY, ON)
            return

        with self._lock_for_last_movement_at:
            now = datetime.datetime.now()
            has_movement = self._last_movement_at and now - self._last_movement_at <= self._thirty_minutes

        use_camera: bool = self.state[USE_CAMERA]

        if not user_is_connected and has_movement:
            if not use_camera:
                self._camera_was_not_used = True
                self._run_command(BotCommands.CAMERA, ON)
        elif self._camera_was_not_used and use_camera:
            self._camera_was_not_used = False
            self._run_command(BotCommands.CAMERA, OFF)
