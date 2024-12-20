import datetime
import io
import logging
import typing

from requests import ReadTimeout

from libs import task_queue

from ...common.exceptions import Shutdown
from ...common.utils import create_plot, is_sleep_hours
from ...signals.models import Signal
from .. import constants, events
from ..utils.wifi import check_if_owner_is_connected_to_router, get_connected_devices_to_router
from .base import BaseSignalHandler, IntervalNotificationCheckMixin
from .utils import get_default_signal_compress_datetime_range


class RouterHandler(IntervalNotificationCheckMixin, BaseSignalHandler):
    task_interval = datetime.timedelta(seconds=10)
    priority = task_queue.TaskPriorities.HIGH
    _check_after: datetime.datetime = datetime.datetime.min
    _errors_count: int = 0
    _timedelta_for_checking: datetime.timedelta = datetime.timedelta(seconds=30)
    _timedelta_for_connection: datetime.timedelta = datetime.timedelta(minutes=2)
    _last_connected_at: datetime.datetime = datetime.datetime.min

    def get_initial_state(self) -> dict[str, typing.Any]:
        devices = ()

        try:
            devices = tuple(get_connected_devices_to_router())
        except Shutdown:
            raise
        except Exception as e:
            logging.exception(e)

        owner_is_connected_to_router = check_if_owner_is_connected_to_router(devices)

        return {
            **super().get_initial_state(),
            constants.USER_IS_CONNECTED_TO_ROUTER: owner_is_connected_to_router,
            constants.USER_IS_AT_HOME: owner_is_connected_to_router,
            constants.CONNECTED_DEVICES_TO_ROUTER: devices,
        }

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self._state.subscribe_toggle(
                constants.USER_IS_CONNECTED_TO_ROUTER,
                {
                    (
                        False,
                        True,
                    ): lambda name: events.user_is_connected_to_router.send(),
                    (
                        True,
                        False,
                    ): lambda name: events.user_is_disconnected_to_router.send(),
                },
            ),
            self._state.subscribe_toggle(
                constants.USER_IS_AT_HOME,
                {
                    (
                        False,
                        True,
                    ): lambda name: events.user_is_at_home.send(),
                    (
                        True,
                        False,
                    ): lambda name: events.user_is_not_at_home.send(),
                },
            ),
        )

    def process(self) -> None:
        now = datetime.datetime.now()
        date_coefficient = 2 if is_sleep_hours() else 1

        need_to_recheck = self._check_after <= now

        if not need_to_recheck:
            return

        devices = None

        try:
            devices = tuple(get_connected_devices_to_router())
        except (
            ConnectionError,
            ReadTimeout,
        ) as e:
            logging.warning(e)
            self._errors_count += 1
        except Exception:
            logging.exception('Unexpected exception in "RouterHandler.process"')
            self._errors_count += 1
        else:
            self._errors_count = 0

        self._state[constants.CONNECTED_DEVICES_TO_ROUTER] = devices
        is_connected = check_if_owner_is_connected_to_router(devices or ())

        if self._errors_count > 0:
            delta = self._timedelta_for_checking * date_coefficient + datetime.timedelta(
                seconds=self._errors_count * 10,
            )
            max_delta = datetime.timedelta(minutes=10) * date_coefficient

            delta = min(delta, max_delta)

            self._check_after = now + delta
        else:
            self._check_after = now + self._timedelta_for_checking * date_coefficient

        Signal.add(signal_type=constants.USER_IS_CONNECTED_TO_ROUTER, value=int(is_connected))

        if is_connected:
            self._last_connected_at = now
            self._state[constants.USER_IS_CONNECTED_TO_ROUTER] = True
            self._state[constants.USER_IS_AT_HOME] = True
        elif self._state[constants.USER_IS_CONNECTED_TO_ROUTER]:
            can_reset_connection = now - self._last_connected_at >= self._timedelta_for_connection * date_coefficient

            if can_reset_connection:
                self._state[constants.USER_IS_CONNECTED_TO_ROUTER] = False

                if self._state[constants.USER_IS_AT_HOME]:
                    device_can_sleep = is_sleep_hours() and now - self._last_connected_at <= datetime.timedelta(hours=8)

                    if device_can_sleep:
                        self._messenger.send_message(
                            'Owner is not connected to the router, but the home presence status has not been changed',
                        )
                    else:
                        self._state[constants.USER_IS_AT_HOME] = False

    def generate_plots(
        self,
        *,
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> typing.Sequence[io.BytesIO] | None:
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
                title='Owner is connected to the router',
                x_attr='received_at',
                y_attr='value',
                stats=stats,
            ),
        )

    def compress(self) -> None:
        Signal.compress(
            constants.USER_IS_CONNECTED_TO_ROUTER,
            datetime_range=get_default_signal_compress_datetime_range(),
            approximation_value=0,
            approximation_time=datetime.timedelta(hours=1),
        )
