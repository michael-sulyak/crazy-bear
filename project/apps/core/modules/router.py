import datetime
import io
import typing

import schedule

from ..base import BaseModule, Command
from ...signals.models import Signal
from ...task_queue import TaskPriorities
from ...common.tplink import TpLinkClient
from ...common.utils import check_user_connection_to_router, create_plot, synchronized
from ...core import constants, events
from ...messengers.constants import BotCommands
from .... import config


__all__ = (
    'Router',
)


class Router(BaseModule):
    _tplink_client: TpLinkClient
    _last_connected_at: datetime.datetime
    _timedelta_for_connection: datetime.timedelta = datetime.timedelta(seconds=30)
    _user_was_connected: typing.Optional[bool] = None
    _last_saving: datetime.datetime
    _timedelta_for_saving: datetime.timedelta = datetime.timedelta(minutes=1)

    _last_checking: datetime.datetime
    _timedelta_for_checking: datetime.timedelta = datetime.timedelta(seconds=10)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.tplink_client = TpLinkClient(
            username=config.ROUTER_USERNAME,
            password=config.ROUTER_PASSWORD,
            url=config.ROUTER_URL,
        )

        now = datetime.datetime.now()
        self._last_connected_at = now
        self._last_saving = now
        self._last_checking = now

    @property
    def initial_state(self) -> typing.Dict[str, typing.Any]:
        return {
            constants.USER_IS_CONNECTED_TO_ROUTER: check_user_connection_to_router(),
        }

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_router_stats),
        )

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(1).seconds.do(
                self.unique_task_queue.push,
                self._check_user_status,
                priority=TaskPriorities.HIGH,
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CONNECTED_DEVICES:
            self._send_connected_devices()
            return True

        return False

    @synchronized
    def _check_user_status(self) -> None:
        now = datetime.datetime.now()

        need_to_recheck = (
                self._user_was_connected is not True
                or now - self._last_checking >= self._timedelta_for_checking
        )

        if not need_to_recheck:
            return

        is_connected = check_user_connection_to_router()

        need_to_save = self._user_was_connected != is_connected or now - self._last_saving >= self._timedelta_for_saving

        if need_to_save:
            Signal.add(signal_type=constants.USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))
            self._user_was_connected = is_connected
            self._last_saving = now

        if is_connected:
            self._last_connected_at = now
            self.state[constants.USER_IS_CONNECTED_TO_ROUTER] = True

        can_reset_connection = now - self._last_connected_at >= self._timedelta_for_connection

        if not is_connected and can_reset_connection:
            self.state[constants.USER_IS_CONNECTED_TO_ROUTER] = False

    @staticmethod
    def _create_router_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                             components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'router_usage' not in components:
            return None

        stats = Signal.get(
            signal_type=constants.USER_IS_CONNECTED_TO_ROUTER,
            date_range=date_range,
        )

        if not stats:
            return None

        return create_plot(title='User is connected to router', x_attr='received_at', y_attr='value', stats=stats)

    def _send_connected_devices(self) -> None:
        connected_devices = self.tplink_client.get_connected_devices()

        message = ''

        for connected_device in connected_devices:
            for key, value in connected_device.items():
                message += f'*{key}:* {value}\n'

            message += '\n'

        self.messenger.send_message(message)
