import datetime
import io
import typing

import schedule
import serial

from ...signals.models import Signal
from ..base import BaseModule, Command
from ..constants import ARDUINO_IS_ENABLED, BotCommands, WEATHER_HUMIDITY, WEATHER_TEMPERATURE
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ArduinoSensorTypes
from ...common.constants import OFF, ON
from ...common.utils import create_plot, synchronized_method
from ...core import events
from ...core.constants import PHOTO, SECURITY_IS_ENABLED, USE_CAMERA
from ...task_queue import TaskPriorities


__all__ = (
    'Arduino',
)


class Arduino(BaseModule):
    initial_state = {
        ARDUINO_IS_ENABLED: False,
    }
    _arduino_connector: typing.Optional[ArduinoConnector] = None

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(1).second.do(
                self.unique_task_queue.push,
                self.check,
                priority=TaskPriorities.HIGH,
            ),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_arduino_sensor_avg_stats),
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
    def check(self) -> None:
        arduino_connector_is_not_active = self._arduino_connector and not self._arduino_connector.is_active

        if arduino_connector_is_not_active:
            self._disable_arduino()
            return

        arduino_connector_is_active = self._arduino_connector and self._arduino_connector.is_active

        if arduino_connector_is_active:
            self._process_arduino_updates()

    @synchronized_method
    def disable(self) -> None:
        super().disable()
        self._disable_arduino()

    @synchronized_method
    def _enable_arduino(self) -> None:
        if self._arduino_connector:
            self.messenger.send_message('Arduino is already on')
            return

        try:
            self._arduino_connector = ArduinoConnector()
            self._arduino_connector.start()
        except serial.SerialException:
            self._arduino_connector = None
            self.state[ARDUINO_IS_ENABLED] = False
            self.messenger.send_message('Arduino can not be connected')
        else:
            self.state[ARDUINO_IS_ENABLED] = True
            self.messenger.send_message('Arduino is on')

    @synchronized_method
    def _disable_arduino(self) -> None:
        self.state[ARDUINO_IS_ENABLED] = False

        if self._arduino_connector:
            self._arduino_connector.finish()
            self._arduino_connector = None
            self.messenger.send_message('Arduino is off')
        else:
            self.messenger.send_message('Arduino is already off')

    @staticmethod
    def _create_arduino_sensor_avg_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                                         components: typing.Set[str]) -> typing.Optional[typing.List[io.BytesIO]]:
        if 'arduino' not in components:
            return None

        humidity_stats = Signal.get_aggregated(ArduinoSensorTypes.HUMIDITY, date_range=date_range)
        temperature_stats = Signal.get_aggregated(ArduinoSensorTypes.TEMPERATURE, date_range=date_range)

        weather_temperature = None
        weather_humidity = None

        if 'extra_data' in components:
            if len(temperature_stats) >= 2:
                weather_humidity = Signal.get_aggregated(
                    signal_type=WEATHER_HUMIDITY,
                    date_range=(humidity_stats[0].received_at, humidity_stats[-1].received_at,),
                )

            if len(temperature_stats) >= 2:
                weather_temperature = Signal.get_aggregated(
                    signal_type=WEATHER_TEMPERATURE,
                    date_range=(temperature_stats[0].received_at, temperature_stats[-1].received_at,),
                )

        plots = []

        if temperature_stats:
            plots.append(create_plot(
                title='Temperature',
                x_attr='aggregated_time',
                y_attr='value',
                stats=temperature_stats,
                additional_plots=(
                    [{'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_temperature}]
                    if weather_temperature else None
                ),
                legend=(
                    ['Inside', 'Outside']
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
                    [{'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_humidity}]
                    if weather_humidity else None
                ),
                legend=(
                    ['Inside', 'Outside']
                    if weather_humidity else None
                ),
            ))

        pir_stats = Signal.get(ArduinoSensorTypes.PIR_SENSOR, date_range=date_range)

        if pir_stats:
            plots.append(create_plot(title='PIR Sensor', x_attr='received_at', y_attr='value', stats=pir_stats))

        return plots

    @synchronized_method
    def _process_arduino_updates(self) -> None:
        if not self._arduino_connector or not self._arduino_connector.is_active:
            return

        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        signals = self._arduino_connector.process_updates()

        if not signals:
            return

        if security_is_enabled:
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

        events.new_arduino_data.send(signals=signals)
