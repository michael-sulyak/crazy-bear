import datetime
import io
import typing

import serial

from ..base import BaseModule, Command
from ..constants import ARDUINO_IS_ENABLED, BotCommands, WEATHER_HUMIDITY, WEATHER_TEMPERATURE
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ArduinoSensorTypes
from ...common.constants import OFF, ON
from ...common.utils import create_plot, synchronized_method
from ...core import events
from ...core.constants import PHOTO, SECURITY_IS_ENABLED, USE_CAMERA
from ...signals.models import Signal
from ...signals.utils import downgrade_signals
from ...task_queue import IntervalTask, TaskPriorities


__all__ = (
    'Arduino',
)


class Arduino(BaseModule):
    initial_state = {
        ARDUINO_IS_ENABLED: False,
    }
    _arduino_connector: typing.Optional[ArduinoConnector] = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._arduino_connector = ArduinoConnector()

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._check_arduino_connector,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(seconds=1),
            ),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_arduino_sensor_avg_stats),
            events.new_arduino_data.connect(self._process_new_arduino_logs),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.ARDUINO:
            if command.first_arg == ON:
                self._enable_arduino()
            elif command.first_arg == OFF:
                self._disable_arduino()
            else:
                return False

            return True

        return False

    @synchronized_method
    def disable(self) -> None:
        super().disable()
        self._disable_arduino()

    @synchronized_method
    def _check_arduino_connector(self) -> None:
        if self.state[ARDUINO_IS_ENABLED]:
            if not self._arduino_connector.is_active:
                self._disable_arduino()
                return

            signals = self._arduino_connector.process_updates()

            if signals:
                events.new_arduino_data.send(signals=signals)

    @synchronized_method
    def _enable_arduino(self) -> None:
        if self._arduino_connector.is_active:
            self.messenger.send_message('Arduino is already on')
            return

        try:
            self._arduino_connector.open()
        except serial.SerialException:
            self.state[ARDUINO_IS_ENABLED] = False
            self.messenger.send_message('Arduino can not be connected')
        else:
            self.state[ARDUINO_IS_ENABLED] = True
            self.messenger.send_message('Arduino is on')

    @synchronized_method
    def _disable_arduino(self) -> None:
        self.state[ARDUINO_IS_ENABLED] = False

        if self._arduino_connector.is_active:
            self._arduino_connector.close()
            self.messenger.send_message('Arduino is off')
        else:
            self.messenger.send_message('Arduino is already off')

    @staticmethod
    def _create_arduino_sensor_avg_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                                         components: typing.Set[str]) -> typing.Optional[typing.List[io.BytesIO]]:
        if 'arduino' not in components:
            return None

        humidity_stats = Signal.get_aggregated(ArduinoSensorTypes.HUMIDITY, datetime_range=date_range)
        temperature_stats = Signal.get_aggregated(ArduinoSensorTypes.TEMPERATURE, datetime_range=date_range)

        weather_temperature = None
        weather_humidity = None

        if 'extra_data' in components:
            if len(temperature_stats) >= 2:
                weather_humidity = Signal.get_aggregated(
                    signal_type=WEATHER_HUMIDITY,
                    datetime_range=(humidity_stats[0].aggregated_time, humidity_stats[-1].aggregated_time,),
                )

            if len(temperature_stats) >= 2:
                weather_temperature = Signal.get_aggregated(
                    signal_type=WEATHER_TEMPERATURE,
                    datetime_range=(temperature_stats[0].aggregated_time, temperature_stats[-1].aggregated_time,),
                )

        plots = []

        if temperature_stats:
            plots.append(create_plot(
                title='Temperature',
                x_attr='aggregated_time',
                y_attr='value',
                stats=temperature_stats,
                additional_plots=(
                    ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_temperature},)
                    if weather_temperature else None
                ),
                legend=(
                    ('Inside', 'Outside',)
                    if weather_temperature else None
                ),
            ))

        if humidity_stats:
            plots.append(create_plot(
                title='Humidity',
                x_attr='aggregated_time',
                y_attr='value',
                stats=humidity_stats,
                additional_plots=(
                    ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_humidity},)
                    if weather_humidity else None
                ),
                legend=(
                    ('Inside', 'Outside',)
                    if weather_humidity else None
                ),
            ))

        pir_stats = Signal.get(ArduinoSensorTypes.PIR_SENSOR, datetime_range=date_range)

        if pir_stats:
            pir_stats = tuple(downgrade_signals(pir_stats))
            plots.append(create_plot(title='PIR Sensor', x_attr='received_at', y_attr='value', stats=pir_stats))

        return plots

    @synchronized_method
    def _process_new_arduino_logs(self, signals: typing.List[Signal]) -> None:
        if self.state[SECURITY_IS_ENABLED]:
            last_movement = None

            for signal in signals:
                if signal.type != ArduinoSensorTypes.PIR_SENSOR:
                    continue

                if signal.value <= 100:
                    continue

                if not last_movement or last_movement.value < signal.value:
                    last_movement = signal

            if last_movement:
                self.messenger.send_message(
                    f'*Detected movement*\n'
                    f'Current pir sensor: `{last_movement.value}`\n'
                    f'Timestamp: `{last_movement.received_at.strftime("%Y-%m-%d, %H:%M:%S")}`'
                )

                if self.state[USE_CAMERA]:
                    self._run_command(BotCommands.CAMERA, PHOTO)

                events.motion_detected.send()
