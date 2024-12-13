import datetime
import io
import threading
import typing
from collections import defaultdict
from functools import partial

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from project.config import SmartDeviceNames

from ...common.utils import create_plot
from ...core import constants
from ...signals.models import Signal
from .base import BaseSignalHandler
from .mixins import ZigBeeDeviceBatteryCheckerMixin
from .utils import get_default_signal_compress_datetime_range


__all__ = ('TemperatureHumiditySensorsHandler',)

HUMIDITY = 'humidity'
TEMPERATURE = 'temperature'


class TemperatureHumiditySensorsHandler(ZigBeeDeviceBatteryCheckerMixin, BaseSignalHandler):
    device_names = (SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM,)
    _lock: threading.RLock
    _last_sent_at_map: dict[str, datetime.datetime]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()
        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.min)

        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.subscribe_on_update(partial(self._process_update, device_name=device_name))

    def compress(self) -> None:
        signal_types = self.device_names
        Signal.clear(signal_types)

        datetime_range = get_default_signal_compress_datetime_range()

        for signal_type in signal_types:
            Signal.compress_by_time(
                signal_type,
                datetime_range=datetime_range,
            )

            Signal.compress(
                signal_type,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )

    def generate_plots(
        self,
        *,
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> typing.Sequence[io.BytesIO] | None:
        if 'arduino' not in components:
            return None

        humidity_stats = Signal.get(HUMIDITY, datetime_range=date_range)
        temperature_stats = Signal.get(TEMPERATURE, datetime_range=date_range)

        weather_temperature = None
        weather_humidity = None

        if 'extra_data' in components:
            if len(temperature_stats) >= 2:
                weather_humidity = Signal.get_aggregated(
                    signal_type=constants.WEATHER_HUMIDITY,
                    datetime_range=(
                        humidity_stats[0].received_at,
                        humidity_stats[-1].received_at,
                    ),
                )

            if len(temperature_stats) >= 2:
                weather_temperature = Signal.get_aggregated(
                    signal_type=constants.WEATHER_TEMPERATURE,
                    datetime_range=(
                        temperature_stats[0].received_at,
                        temperature_stats[-1].received_at,
                    ),
                )

        plots = []

        if temperature_stats:
            plots.append(
                create_plot(
                    title='Temperature',
                    x_attr='received_at',
                    y_attr='value',
                    stats=temperature_stats,
                    additional_plots=(
                        ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_temperature},)
                        if weather_temperature
                        else None
                    ),
                    legend=(
                        (
                            'Inside',
                            'Outside',
                        )
                        if weather_temperature
                        else None
                    ),
                ),
            )

        if humidity_stats:
            plots.append(
                create_plot(
                    title='Humidity',
                    x_attr='received_at',
                    y_attr='value',
                    stats=humidity_stats,
                    additional_plots=(
                        ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_humidity},)
                        if weather_humidity
                        else None
                    ),
                    legend=(
                        (
                            'Inside',
                            'Outside',
                        )
                        if weather_humidity
                        else None
                    ),
                ),
            )

        return plots

    def disable(self) -> None:
        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.unsubscribe()

    @synchronized_method
    def _process_update(self, state: dict, *, device_name: str) -> None:
        if device_name == SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM:
            now = get_current_time()

            Signal.bulk_add((
                Signal(type=TEMPERATURE, value=state['temperature'], received_at=now),
                Signal(type=HUMIDITY, value=state['humidity'], received_at=now),
            ))

            self._process_main_sensor(state)

        self._check_battery(state['battery'], device_name=device_name)

    def _process_main_sensor(self, state: dict) -> None:
        temperature = state['temperature']
        humidity = state['humidity']

        can_send_warning = self._can_send_warning('humidity', datetime.timedelta(hours=3))

        if humidity < 30 and can_send_warning:
            self._messenger.send_message(f'There is low humidity in the room ({humidity}%)!')
            self._mark_as_sent('humidity')

        if humidity > 70 and can_send_warning:
            self._messenger.send_message(f'There is high humidity in the room ({humidity}%)!')
            self._mark_as_sent('humidity')

        can_send_warning = self._can_send_warning('temperature', datetime.timedelta(hours=3))

        if temperature < 18 and can_send_warning:
            self._messenger.send_message(f'There is a low temperature in the room ({temperature})!')
            self._mark_as_sent('temperature')

        if temperature > 28 and can_send_warning:
            self._messenger.send_message(f'There is a high temperature in the room ({temperature})!')
            self._mark_as_sent('temperature')

    def _can_send_warning(self, name: str, timedelta_for_sending: datetime.timedelta) -> bool:
        now = datetime.datetime.now()
        return now - self._last_sent_at_map[name] > timedelta_for_sending

    def _mark_as_sent(self, name: str) -> None:
        now = datetime.datetime.now()
        self._last_sent_at_map[name] = now
