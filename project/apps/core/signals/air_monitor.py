import datetime
import typing

from libs.qingping.base import CleargrassClient

from .... import config
from ...signals.models import Signal
from .. import constants
from .base import BaseSignalHandler, IntervalCheckMixin, NotificationParams, SignalNotificationMixin


class AirMonitorHandler(SignalNotificationMixin, IntervalCheckMixin, BaseSignalHandler):
    task_interval = datetime.timedelta(minutes=5)
    has_init_run = True
    list_of_notification_params = (
        NotificationParams(
            condition=lambda x: x > 1_500,
            message='Very high CO2 levels in the room. Need to ventilate!',
            delay=datetime.timedelta(hours=1),
        ),
        NotificationParams(
            condition=lambda x: x > 1_000,
            message='High CO2 levels in the room. Need to ventilate!',
            delay=datetime.timedelta(hours=2),
        ),
    )

    _client: CleargrassClient

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._client = CleargrassClient(
            app_key=config.QINGPING_APP_KEY,
            app_secret=config.QINGPING_APP_SECRET,
        )

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {
            **super().get_initial_state(),
            constants.AIR_MONITOR_STATE: None,
        }

    def process_by_interval(self) -> None:
        latest_measurement = self._client.get_latest_measurement(config.QINGPING_DEVICE_MAC)

        assert latest_measurement is not None and latest_measurement.measured_at is not None

        self._state[constants.AIR_MONITOR_STATE] = latest_measurement

        signals = []

        if latest_measurement.temperature_celsius is not None:
            signals.append(Signal(
                type=constants.AIR_MONITOR_TEMPERATURE,
                value=latest_measurement.temperature_celsius,
                received_at=latest_measurement.measured_at,
            ))

        if latest_measurement.humidity_percent is not None:
            signals.append(Signal(
                type=constants.AIR_MONITOR_HUMIDITY,
                value=latest_measurement.humidity_percent,
                received_at=latest_measurement.measured_at,
            ))

        if latest_measurement.co2 is not None:
            signals.append(Signal(
                type=constants.AIR_MONITOR_CO2,
                value=latest_measurement.co2,
                received_at=latest_measurement.measured_at,
            ))

        if latest_measurement.pm25 is not None:
            signals.append(Signal(
                type=constants.AIR_MONITOR_PM25,
                value=latest_measurement.pm25,
                received_at=latest_measurement.measured_at,
            ))

        if latest_measurement.pm10 is not None:
            signals.append(Signal(
                type=constants.AIR_MONITOR_PM10,
                value=latest_measurement.pm10,
                received_at=latest_measurement.measured_at,
            ))

        Signal.bulk_add(signals)

        if latest_measurement.co2 is not None:
            self._check_notifications(latest_measurement.co2)
