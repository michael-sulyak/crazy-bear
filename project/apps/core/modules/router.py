import datetime
import io
import logging
import typing

from ..base import BaseModule, Command
from ..constants import BotCommands
from ...common.routers.mi import mi_wifi
from ...common.routers.tplink import TpLink
from ...common.utils import create_plot, is_sleep_hours, synchronized_method
from ...core import constants, events
from ...devices.utils import check_if_host_is_at_home
from ...signals.models import Signal
from ...task_queue import IntervalTask, TaskPriorities
from .... import config


__all__ = (
    'Router',
)


class Router(BaseModule):
    _last_connected_at: datetime.datetime
    _timedelta_for_connection: datetime.timedelta = datetime.timedelta(seconds=10)

    _check_after: datetime.datetime
    _errors_count: int = 0
    _timedelta_for_checking: datetime.timedelta = datetime.timedelta(seconds=10)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()

        self._last_connected_at = now
        self._check_after = now

    @property
    def initial_state(self) -> typing.Dict[str, typing.Any]:
        host_is_at_home = False

        try:
            host_is_at_home = check_if_host_is_at_home()
        except Exception as e:
            logging.exception(e)

        return {
            constants.USER_IS_CONNECTED_TO_ROUTER: host_is_at_home,
        }

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self.state.subscribe_toggle(constants.USER_IS_CONNECTED_TO_ROUTER, {
                (False, True,): lambda name: events.user_is_connected_to_router.send(),
                (True, False,): lambda name: events.user_is_disconnected_to_router.send(),
                (None, True,): lambda name: events.user_is_connected_to_router.send(),
            }),
            events.request_for_statistics.connect(self._create_router_stats),
            events.check_if_user_is_at_home.connect(self._check_user_status),
        )

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=events.check_if_user_is_at_home.send,
                priority=TaskPriorities.HIGH,
                interval=datetime.timedelta(seconds=5),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RAW_WIFI_DEVICES:
            self._send_wifi_connected_devices()
            return True

        return False

    @synchronized_method
    def _check_user_status(self, *, force: bool = False) -> None:
        now = datetime.datetime.now()

        need_to_recheck = force or self._check_after <= now

        if not need_to_recheck:
            return

        try:
            is_connected = check_if_host_is_at_home()
        except Exception as e:
            logging.exception(e)
            is_connected = False
            self._errors_count += 1
        else:
            self._errors_count = 0

        if self._errors_count > 0:
            delta = self._timedelta_for_checking + datetime.timedelta(seconds=self._errors_count * 10)

            if delta > datetime.timedelta(minutes=10):
                delta = datetime.timedelta(minutes=10)

            self._check_after = now + delta
        elif is_sleep_hours():
            self._check_after = now + self._timedelta_for_checking + datetime.timedelta(seconds=10)
        else:
            self._check_after = now + self._timedelta_for_checking

        Signal.add(signal_type=constants.USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))
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
            datetime_range=date_range,
        )

        if not stats:
            return None

        return create_plot(title='User is connected to router', x_attr='received_at', y_attr='value', stats=stats)

    def _send_wifi_connected_devices(self) -> None:
        message = ''

        if config.ROUTER_TYPE == 'tplink':
            tplink_client = TpLink(
                username=config.ROUTER_USERNAME,
                password=config.ROUTER_PASSWORD,
                url=config.ROUTER_URL,
            )

            connected_devices = tplink_client.get_connected_devices()

            for connected_device in connected_devices:
                for key, value in connected_device.items():
                    message += f'*{key}:* {value}\n'

                message += '\n'
        elif config.ROUTER_TYPE == 'mi':
            for device in mi_wifi.device_list()['list']:
                for key, value in device.items():
                    message += f'*{key}:* {value}\n'

                message += '\n'

        self.messenger.send_message(message)
