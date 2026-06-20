import datetime
import typing

from libs.qingping.base import CleargrassClient

from .... import config
from ...common.utils import get_proxy_for_requests
from ...signals.models import Signal
from .. import constants
from .base import BaseSignalHandler, IntervalCheckMixin


class AirMonitorHandler(IntervalCheckMixin, BaseSignalHandler):
    task_interval = datetime.timedelta(minutes=5)
    has_init_run = True

    _client: CleargrassClient

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._client = CleargrassClient(
            app_key=config.QINGPING_APP_KEY,
            app_secret=config.QINGPING_APP_SECRET,
            proxies=get_proxy_for_requests(),
        )

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {
            **super().get_initial_state(),
            constants.AIR_MONITOR_STATE: None,
        }

    def process(self) -> None:
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
