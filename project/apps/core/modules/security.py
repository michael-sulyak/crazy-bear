import datetime
import typing

from libs.casual_utils.parallel_computing import single_synchronized, synchronized_method
from libs.task_queue import IntervalTask, TaskPriorities
from .. import events
from ..base import BaseModule, Command
from ..constants import (
    AUTO_SECURITY_IS_ENABLED, BotCommands, CAMERA_IS_AVAILABLE, SECURITY_IS_ENABLED, USER_IS_CONNECTED_TO_ROUTER,
    USE_CAMERA,
)
from ...common import interface
from ...common.constants import AUTO, OFF, ON


__all__ = (
    'Security',
)


@interface.module(
    title='Security',
    description=(
        'The module turns on the security mode and the camera after the owner leaves the house.'
    ),
)
class Security(BaseModule):
    initial_state = {
        AUTO_SECURITY_IS_ENABLED: False,
        SECURITY_IS_ENABLED: False,
    }
    _last_movement_at: typing.Optional[datetime.datetime] = None
    _camera_was_not_used: bool = False
    _twenty_minutes: datetime.timedelta = datetime.timedelta(minutes=20)

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._check_camera_status,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=1),
            ),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self.state.subscribe_toggle(SECURITY_IS_ENABLED, {
                (False, True,): lambda name: events.security_is_enabled.send(),
                (True, False,): lambda name: events.security_is_disabled.send(),
                (None, True,): lambda name: events.security_is_enabled.send(),
            }),
            events.motion_detected.connect(self._update_last_movement_at),
            events.security_is_enabled.connect(lambda: self.messenger.send_message('Security is enabled')),
            events.security_is_disabled.connect(lambda: self.messenger.send_message('Security is disabled')),
        )

    @synchronized_method
    def disable(self) -> None:
        super().disable()

        if self.state[AUTO_SECURITY_IS_ENABLED]:
            self._disable_auto_security()

    @interface.command(BotCommands.SECURITY, ON)
    @synchronized_method
    def _enable_security(self) -> None:
        self.state[SECURITY_IS_ENABLED] = True

    @interface.command(BotCommands.SECURITY, OFF)
    @synchronized_method
    def _disable_security(self) -> None:
        self.state[SECURITY_IS_ENABLED] = False

    @interface.command(BotCommands.SECURITY, AUTO, ON)
    @synchronized_method
    def _enable_auto_security(self) -> None:
        if self.state[AUTO_SECURITY_IS_ENABLED]:
            self.messenger.send_message('Auto security is already enabled')
            return

        self.state[AUTO_SECURITY_IS_ENABLED] = True

        events.user_is_connected_to_router.connect(self._process_user_is_connected_to_router)
        events.user_is_disconnected_to_router.connect(self._process_user_is_disconnected_to_router)

        self.messenger.send_message('Auto security is enabled')

        if not self.state[USER_IS_CONNECTED_TO_ROUTER]:
            self._process_user_is_disconnected_to_router()

    @interface.command(BotCommands.SECURITY, AUTO, OFF)
    @synchronized_method
    def _disable_auto_security(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            self.messenger.send_message('Auto security is already disabled')
            return

        self.state[AUTO_SECURITY_IS_ENABLED] = False

        if self._camera_was_not_used and self.state[USE_CAMERA]:
            self._run_command(BotCommands.CAMERA, OFF)

        self._camera_was_not_used = False

        events.user_is_connected_to_router.disconnect(self._process_user_is_connected_to_router)
        events.user_is_disconnected_to_router.disconnect(self._process_user_is_disconnected_to_router)

        self.messenger.send_message('Auto security is disabled')

    @synchronized_method
    def _update_last_movement_at(self, source: str) -> None:
        self._last_movement_at = datetime.datetime.now()

        if (
            not self.state[USER_IS_CONNECTED_TO_ROUTER]
            and not self.state[USE_CAMERA]
            and self.state[CAMERA_IS_AVAILABLE]
        ):
            self._camera_was_not_used = True
            self._run_command(BotCommands.CAMERA, ON)

    def _process_user_is_connected_to_router(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        if self.state[SECURITY_IS_ENABLED]:
            self.messenger.send_message('The owner is found')
            self._run_command(BotCommands.SECURITY, OFF)

    def _process_user_is_disconnected_to_router(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        if not self.state[SECURITY_IS_ENABLED]:
            self.messenger.send_message('The owner is not found')
            self._run_command(BotCommands.SECURITY, ON)

    @single_synchronized
    def _check_camera_status(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        now = datetime.datetime.now()
        has_movement = self._last_movement_at and now - self._last_movement_at <= self._twenty_minutes

        user_is_connected: bool = self.state[USER_IS_CONNECTED_TO_ROUTER]
        use_camera: bool = self.state[USE_CAMERA]

        if (user_is_connected or not has_movement) and self._camera_was_not_used and use_camera:
            self._camera_was_not_used = False
            self._run_command(BotCommands.CAMERA, OFF)
