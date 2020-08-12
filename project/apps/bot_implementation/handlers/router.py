import datetime
import typing

from .. import constants
from .. import events
from ..constants import USER_IS_CONNECTED_TO_ROUTER
from ...common.models import Signal
from ...common.utils import check_user_connection_to_router
from ...common.utils import send_plot
from ...messengers.base import BaseCommandHandler, Command


__all__ = (
    'Router',
)


class Router(BaseCommandHandler):
    support_commands = {
        constants.BotCommands.STATS,
    }
    _last_connected_at: datetime.datetime
    _need_initialization: bool = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()
        self._last_connected_at = now

    def init_state(self) -> None:
        self.state.create_many(**{
            USER_IS_CONNECTED_TO_ROUTER: check_user_connection_to_router(),
        })

    def init_schedule(self) -> None:
        self.scheduler.every(1).hours.do(lambda: Signal.clear(signal_type=USER_IS_CONNECTED_TO_ROUTER))

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.STATS:
            self._show_stats(command)

    def update(self) -> None:
        now = datetime.datetime.now()
        is_connected = check_user_connection_to_router()
        Signal.add(signal_type=USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))

        if self._need_initialization:
            self.state[USER_IS_CONNECTED_TO_ROUTER] = is_connected
            self._need_initialization = False

            if is_connected:
                events.user_is_connected_to_router.send()
            else:
                events.user_is_disconnected_to_router.send()
        elif is_connected:
            if not self.state[USER_IS_CONNECTED_TO_ROUTER]:
                self.state[USER_IS_CONNECTED_TO_ROUTER] = True
                self._last_connected_at = now
                events.user_is_connected_to_router.send()
        elif now - self._last_connected_at >= datetime.timedelta(seconds=20):
            if self.state[USER_IS_CONNECTED_TO_ROUTER]:
                self.state[USER_IS_CONNECTED_TO_ROUTER] = False
                events.user_is_disconnected_to_router.send()

    def _show_stats(self, command: Command) -> None:
        stats = Signal.get_avg(
            signal_type=USER_IS_CONNECTED_TO_ROUTER,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if stats:
            send_plot(messenger=self.messenger, stats=stats, title='User is connected to router', attr='value')
