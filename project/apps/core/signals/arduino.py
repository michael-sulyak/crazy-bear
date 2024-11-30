import datetime
import io
import threading
import typing
from collections import defaultdict

from libs.casual_utils.parallel_computing import synchronized_method

from ...arduino.constants import ArduinoSensorTypes
from ...common.events import Receiver
from ...common.utils import create_plot
from ...core import constants
from ...signals.models import Signal
from .. import events
from .base import BaseSignalHandler
from .utils import get_default_signal_compress_datetime_range


class ArduinoHandler(BaseSignalHandler):
    _lock: threading.RLock
    _last_sent_at_map: dict[str, datetime.datetime]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()
        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.min)

    def get_signals(self) -> tuple[Receiver, ...]:
        return (
            *super().get_signals(),
            events.new_arduino_data.connect(self.process_arduino_signals),
        )

    def process_arduino_signals(self, signals: typing.Sequence[Signal]) -> None:
        Signal.bulk_add(signals)
        self._process_new_arduino_logs(signals)

    def compress(self) -> None:
        signal_types = (
            ArduinoSensorTypes.TEMPERATURE,
            ArduinoSensorTypes.HUMIDITY,
            ArduinoSensorTypes.PIR_SENSOR,
        )

        Signal.clear(signal_types)

        datetime_range = get_default_signal_compress_datetime_range()

        for signal_type in signal_types:
            if signal_type == ArduinoSensorTypes.PIR_SENSOR:
                Signal.compress(
                    signal_type,
                    datetime_range=datetime_range,
                    approximation_value=20,
                    approximation_time=datetime.timedelta(minutes=10),
                )
                continue

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

        humidity_stats = Signal.get_aggregated(ArduinoSensorTypes.HUMIDITY, datetime_range=date_range)
        temperature_stats = Signal.get_aggregated(ArduinoSensorTypes.TEMPERATURE, datetime_range=date_range)

        weather_temperature = None
        weather_humidity = None

        if 'extra_data' in components:
            if len(temperature_stats) >= 2:
                weather_humidity = Signal.get_aggregated(
                    signal_type=constants.WEATHER_HUMIDITY,
                    datetime_range=(
                        humidity_stats[0].aggregated_time,
                        humidity_stats[-1].aggregated_time,
                    ),
                )

            if len(temperature_stats) >= 2:
                weather_temperature = Signal.get_aggregated(
                    signal_type=constants.WEATHER_TEMPERATURE,
                    datetime_range=(
                        temperature_stats[0].aggregated_time,
                        temperature_stats[-1].aggregated_time,
                    ),
                )

        plots = []

        if temperature_stats:
            plots.append(
                create_plot(
                    title='Temperature',
                    x_attr='aggregated_time',
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
                )
            )

        if humidity_stats:
            plots.append(
                create_plot(
                    title='Humidity',
                    x_attr='aggregated_time',
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
                )
            )

        pir_stats = Signal.get(ArduinoSensorTypes.PIR_SENSOR, datetime_range=date_range)

        if pir_stats:
            plots.append(create_plot(title='PIR Sensor', x_attr='received_at', y_attr='value', stats=pir_stats))

        return plots

    @synchronized_method
    def _process_new_arduino_logs(self, signals: list[Signal]) -> None:
        last_signal_data: dict[str, typing.Any] = {}

        for signal in reversed(signals):
            if signal.value is None:
                continue

            if signal.type in last_signal_data:
                if last_signal_data.keys() >= {ArduinoSensorTypes.HUMIDITY, ArduinoSensorTypes.TEMPERATURE}:
                    break

                continue

            last_signal_data[signal.type] = signal.value  # type: ignore

        humidity = last_signal_data.get(ArduinoSensorTypes.HUMIDITY)
        temperature = last_signal_data.get(ArduinoSensorTypes.TEMPERATURE)

        if humidity is not None:
            can_send_warning = self._can_send_warning('humidity', datetime.timedelta(hours=3))

            if humidity < 30 and can_send_warning:
                self._messenger.send_message(f'There is low humidity in the room ({humidity}%)!')
                self._mark_as_sent('humidity')

            if humidity > 70 and can_send_warning:
                self._messenger.send_message(f'There is high humidity in the room ({humidity}%)!')
                self._mark_as_sent('humidity')

        if temperature is not None:
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
