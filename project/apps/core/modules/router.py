import datetime
import io
import typing

import schedule

from ..base import BaseModule, Command
from ...common.models import Signal
from ...common.tplink import TpLinkClient
from ...common.utils import check_user_connection_to_router, create_plot, synchronized
from ...core import events
from ...core.constants import USER_IS_CONNECTED_TO_ROUTER
from ...messengers.constants import BotCommands
from .... import config


__all__ = (
    'Router',
)


class Router(BaseModule):
    _last_connected_at: datetime.datetime
    _need_initialization: bool = True
    _timedelta_for_connection: datetime.timedelta = datetime.timedelta(seconds=30)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()
        self._last_connected_at = now

    @property
    def initial_state(self) -> typing.Dict[str, typing.Any]:
        return {
            USER_IS_CONNECTED_TO_ROUTER: check_user_connection_to_router(),
        }

    def connect_to_events(self) -> None:
        super().connect_to_events()

        events.request_for_statistics.connect(self._create_router_stats)

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(1).hours.do(
                self.task_queue.push,
                lambda: Signal.clear(signal_type=USER_IS_CONNECTED_TO_ROUTER),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CONNECTED_DEVICES:
            self._send_connected_devices()
            return True

        return False

    @synchronized
    def tick(self) -> None:
        is_connected = check_user_connection_to_router()
        Signal.add(signal_type=USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))
        now = datetime.datetime.now()

        if self._need_initialization:
            self.state[USER_IS_CONNECTED_TO_ROUTER] = is_connected
            self._need_initialization = False
        elif is_connected:
            self._last_connected_at = now

            if not self.state[USER_IS_CONNECTED_TO_ROUTER]:
                self.state[USER_IS_CONNECTED_TO_ROUTER] = True
        elif now - self._last_connected_at >= self._timedelta_for_connection:
            if self.state[USER_IS_CONNECTED_TO_ROUTER]:
                self.state[USER_IS_CONNECTED_TO_ROUTER] = False

    @staticmethod
    def _create_router_stats(command: Command) -> typing.Optional[io.BytesIO]:
        stats = Signal.get(
            signal_type=USER_IS_CONNECTED_TO_ROUTER,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not stats:
            return None

        return create_plot(title='User is connected to router', x_attr='time', y_attr='value', stats=stats)

    def _send_connected_devices(self) -> None:
        tplink_client = TpLinkClient(
            username=config.ROUTER_USERNAME,
            password=config.ROUTER_PASSWORD,
            url=config.ROUTER_URL,
        )

        connected_devices = tplink_client.get_connected_devices()

        message = ''

        for connected_device in connected_devices:
            for key, value in connected_device.items():
                message += f'*{key}:* {value}\n'

            message += '\n'

        self.messenger.send_message(message)
