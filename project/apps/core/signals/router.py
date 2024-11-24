import datetime
import io
import logging
import threading
import typing

from requests import ReadTimeout

from libs import task_queue
from libs.casual_utils.parallel_computing import synchronized_method
from .base import BaseAdvancedSignalHandler
from .. import constants, events
from ..utils.wifi import check_if_host_is_at_home
from ...common.events import Receiver
from ...common.exceptions import Shutdown
from ...common.utils import create_plot, is_sleep_hours
from ...signals.models import Signal


class RouterHandler(BaseAdvancedSignalHandler):
    task_interval = datetime.timedelta(seconds=10)
    priority = task_queue.TaskPriorities.HIGH
    signal_type = constants.USER_IS_CONNECTED_TO_ROUTER
    compress_by_time = False
    _lock: threading.RLock
    _check_after: datetime.datetime = datetime.datetime.min
    _errors_count: int = 0
    _timedelta_for_checking: datetime.timedelta = datetime.timedelta(seconds=30)
    _timedelta_for_connection: datetime.timedelta = datetime.timedelta(minutes=2)
    _last_connected_at: datetime.datetime = datetime.datetime.min

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()

    def get_signals(self) -> tuple[Receiver, ...]:
        return (
            *super().get_signals(),
            events.check_if_user_is_at_home.connect(self.process),
        )

    def get_value(self) -> typing.Any:
        pass

    @synchronized_method
    def process(self) -> None:
        now = datetime.datetime.now()
        date_coefficient = 2 if is_sleep_hours() else 1

        need_to_recheck = self._check_after <= now

        if not need_to_recheck:
            return

        try:
            is_connected = check_if_host_is_at_home()
        except Shutdown:
            raise
        except (
            ConnectionError,
            ReadTimeout,
        ) as e:
            logging.warning(e)
            is_connected = False
            self._errors_count += 1
        except Exception as e:
            logging.exception(e)
            is_connected = False
            self._errors_count += 1
        else:
            self._errors_count = 0

        if self._errors_count > 0:
            delta = self._timedelta_for_checking * date_coefficient + datetime.timedelta(seconds=self._errors_count * 10)

            if delta > datetime.timedelta(minutes=10):
                delta = datetime.timedelta(minutes=10)

            self._check_after = now + delta
        else:
            self._check_after = now + self._timedelta_for_checking * date_coefficient

        Signal.add(signal_type=constants.USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))

        if is_connected:
            self._last_connected_at = now
            self._state[constants.USER_IS_CONNECTED_TO_ROUTER] = True

        can_reset_connection = now - self._last_connected_at >= self._timedelta_for_connection * date_coefficient

        if not is_connected and can_reset_connection:
            self._state[constants.USER_IS_CONNECTED_TO_ROUTER] = False

    def generate_plots(
        self, *, date_range: tuple[datetime.datetime, datetime.datetime], components: typing.Set[str]
    ) -> typing.Optional[typing.Sequence[io.BytesIO]]:

        if 'router_usage' not in components:
            return None

        stats = Signal.get(
            signal_type=constants.USER_IS_CONNECTED_TO_ROUTER,
            datetime_range=date_range,
        )

        if not stats:
            return None

        return (
            create_plot(
                title='User is connected to router',
                x_attr='received_at',
                y_attr='value',
                stats=stats,
            ),
        )
