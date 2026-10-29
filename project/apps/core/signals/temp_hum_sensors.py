import datetime
import io
import logging
import typing
from collections import defaultdict

from ....config import SmartDeviceNames
from ...common.utils import create_plot, get_zigbee_device_names_to_ignore_availability
from ...core import constants
from ...signals.models import Signal
from .base import BaseSimpleSensorStateHandler
from .utils import get_default_signal_compress_datetime_range


__all__ = ('TemperatureHumiditySensorsHandler',)

TEMPERATURE_SUFFIX = ':temperature'
HUMIDITY_SUFFIX = ':humidity'

TEMPERATURE = f'{SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM}{TEMPERATURE_SUFFIX}'
HUMIDITY = f'{SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM}{HUMIDITY_SUFFIX}'


class TemperatureHumiditySensorsHandler(BaseSimpleSensorStateHandler):
    device_names = SmartDeviceNames.TEMP_HUM_SENSORS
    _last_sent_at_map: dict[str, datetime.datetime]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.min)

    def handle_sensor_state(self, *, state: dict, device_name: str, received_at: datetime.datetime) -> None:
        if device_name in get_zigbee_device_names_to_ignore_availability():
            logging.error(f'Device {device_name} ignored',
                          extra={'state': state, 'device_name': device_name, 'received_at': received_at.isoformat()})
            return

        Signal.bulk_add((
            Signal(type=f'{device_name}{TEMPERATURE_SUFFIX}', value=state['temperature'], received_at=received_at),
            Signal(type=f'{device_name}{HUMIDITY_SUFFIX}', value=state['humidity'], received_at=received_at),
        ))

        self._check_state(state, device_name=device_name)
        self._check_battery(state.get('battery'), device_name=device_name)

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

    def _check_state(self, state: dict, *, device_name: str) -> None:
        temperature = state['temperature']
        humidity = state['humidity']

        if device_name == SmartDeviceNames.TEMP_HUM_SENSOR_LOGGIA:
            temperature_range = (10, 40)
            humidity_range = (0, 85)
        else:
            temperature_range = (16, 28)
            humidity_range = (25, 70)

        can_send_warning = self._can_send_warning(f'temperature_{device_name}', datetime.timedelta(hours=3))

        if temperature < temperature_range[0] and can_send_warning:
            self._messenger.send_message(f'There is a low temperature in room "{device_name}" ({temperature})!')
            self._mark_as_sent(f'temperature_{device_name}')

        if temperature > temperature_range[1] and can_send_warning:
            self._messenger.send_message(f'There is a high temperature in room "{device_name}" ({temperature})!')
            self._mark_as_sent(f'temperature_{device_name}')

        can_send_warning = self._can_send_warning(f'humidity_{device_name}', datetime.timedelta(hours=3))

        if humidity < humidity_range[0] and can_send_warning:
            self._messenger.send_message(f'There is low humidity in room "{device_name}" ({humidity}%)!')
            self._mark_as_sent(f'humidity_{device_name}')

        if humidity > humidity_range[1] and can_send_warning:
            self._messenger.send_message(f'There is high humidity in room "{device_name}" ({humidity}%)!')
            self._mark_as_sent(f'humidity_{device_name}')

    def _can_send_warning(self, name: str, timedelta_for_sending: datetime.timedelta) -> bool:
        now = datetime.datetime.now()
        return now - self._last_sent_at_map[name] > timedelta_for_sending

    def _mark_as_sent(self, name: str) -> None:
        now = datetime.datetime.now()
        self._last_sent_at_map[name] = now
