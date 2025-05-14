import datetime
import io
import threading
import typing
from collections import defaultdict
from functools import cached_property

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.task_queue import TaskPriorities
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from project.config import SmartDeviceNames

from ...common.utils import create_plot
from ...core import constants
from ...signals.models import Signal
from .base import BaseSignalHandler
from .mixins import ZigBeeDeviceBatteryCheckerMixin
from .utils import get_default_signal_compress_datetime_range


__all__ = ('TemperatureHumiditySensorsHandler',)

TEMPERATURE_SUFFIX = ':temperature'
HUMIDITY_SUFFIX = ':humidity'

TEMPERATURE = f'{SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM}{TEMPERATURE_SUFFIX}'
HUMIDITY = f'{SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM}{HUMIDITY_SUFFIX}'


class TemperatureHumiditySensorsHandler(ZigBeeDeviceBatteryCheckerMixin, BaseSignalHandler):
    device_names = SmartDeviceNames.TEMP_HUM_SENSORS
    _lock: threading.RLock
    _last_sent_at_map: dict[str, datetime.datetime]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()
        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.min)

        for sensor in self._sensors:
            sensor.subscribe_on_update(
                lambda state, device_name=sensor.friendly_name: self._task_queue.put(
                    self._process_update,
                    kwargs={'state': state, 'device_name': device_name, 'received_at': get_current_time()},
                    priority=TaskPriorities.HIGH,
                ),
            )

    @cached_property
    def _sensors(self) -> tuple[ZigBeeDeviceWithOnlyState, ...]:
        return tuple(
            self._context.smart_devices_map[device_name]
            for device_name in self.device_names
        )

    def compress(self) -> None:
        datetime_range = get_default_signal_compress_datetime_range()

        for signal_type in self.device_names:
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

        plots = []

        for device_name in self.device_names:
            place_name = device_name.removeprefix(SmartDeviceNames.TEMP_HUM_SENSOR_NAME_PREFIX)
            temperature_stats = Signal.get(f'{device_name}{TEMPERATURE_SUFFIX}', datetime_range=date_range)
            humidity_stats = Signal.get(f'{device_name}{HUMIDITY_SUFFIX}', datetime_range=date_range)

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

            if temperature_stats:
                plots.append(
                    create_plot(
                        title=f'Temperature ({place_name})',
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
                        title=f'Humidity ({place_name})',
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
        for sensor in self._sensors:
            sensor.unsubscribe()

    @synchronized_method
    def _process_update(self, state: dict, *, device_name: str, received_at: datetime.datetime) -> None:
        Signal.bulk_add((
            Signal(type=f'{device_name}{TEMPERATURE_SUFFIX}', value=state['temperature'], received_at=received_at),
            Signal(type=f'{device_name}{HUMIDITY_SUFFIX}', value=state['humidity'], received_at=received_at),
        ))

        if device_name == SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM:
            self._process_main_sensor(state)

        self._check_battery(state.get('battery'), device_name=device_name)

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
