import queue
import typing

import serial

from .. import constants
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ARDUINO_CONNECTOR, ARDUINO_IS_ENABLED
from ...arduino.models import ArduinoLog
from ...common.utils import send_plot
from ...guard.constants import SECURITY_IS_ENABLED, USE_CAMERA
from ...messengers.base import BaseBotCommandHandler, MessengerCommand, MessengerUpdate
from ...messengers.constants import UPDATES


__all__ = (
    'Arduino',
)


class Arduino(BaseBotCommandHandler):
    support_commands = {
        constants.BotCommands.ARDUINO,
        constants.BotCommands.STATS,
    }

    def init_state(self) -> None:
        self.state.create_many({
            ARDUINO_CONNECTOR: None,
            ARDUINO_IS_ENABLED: False,
        })

    def process_command(self, command: MessengerCommand) -> None:
        if command.name == constants.BotCommands.ARDUINO:
            if command.first_arg == 'on':
                self._enable_arduino()
            elif command.first_arg == 'off':
                self._disable_arduino()
        elif command.name == constants.BotCommands.STATS:
            self._show_stats(command)

    def update(self) -> None:
        arduino_connector: typing.Optional[ArduinoConnector] = self.state[ARDUINO_CONNECTOR]

        if arduino_connector and not arduino_connector.is_active:
            self._disable_arduino()
            arduino_connector = None

        if arduino_connector:
            self._process_arduino_updates()

    def clear(self) -> None:
        self._disable_arduino()

    def _enable_arduino(self) -> None:
        arduino_connector: ArduinoConnector = self.state[ARDUINO_CONNECTOR]

        if arduino_connector:
            self.messenger.send_message('Arduino is already on')
            return

        arduino_connector = ArduinoConnector()
        self.state[ARDUINO_CONNECTOR] = arduino_connector

        try:
            arduino_connector.start()
        except serial.SerialException:
            self.state.clear(ARDUINO_CONNECTOR)
            self.state.set_false(ARDUINO_IS_ENABLED)
            self.messenger.send_message('Arduino can not be connected')
        else:
            self.state.set_true(ARDUINO_IS_ENABLED)
            self.messenger.send_message('Arduino is on')

    def _disable_arduino(self) -> None:
        arduino_connector: ArduinoConnector = self.state[ARDUINO_CONNECTOR]
        self.state.set_false(ARDUINO_IS_ENABLED)

        if not arduino_connector:
            self.messenger.send_message('Arduino is already off')
            return

        arduino_connector.finish()
        self.state.clear(ARDUINO_CONNECTOR)
        self.messenger.send_message('Arduino is off')

    def _show_stats(self, command: MessengerCommand) -> None:
        arduino_connector: ArduinoConnector = self.state[ARDUINO_CONNECTOR]

        if not arduino_connector:
            return

        stats = ArduinoLog.get_avg(
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not stats:
            return

        send_plot(messenger=self.messenger, stats=stats, title='PIR Sensor', attr='pir_sensor')
        send_plot(messenger=self.messenger, stats=stats, title='Humidity', attr='humidity')
        send_plot(messenger=self.messenger, stats=stats, title='Temperature', attr='temperature')

    def _process_arduino_updates(self) -> None:
        arduino_connector: typing.Optional[ArduinoConnector] = self.state[ARDUINO_CONNECTOR]

        if not arduino_connector:
            return

        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        new_arduino_logs = arduino_connector.process_updates()

        if not security_is_enabled or not new_arduino_logs:
            return

        last_movement = None

        for arduino_log in reversed(new_arduino_logs):
            if arduino_log.pir_sensor > 0:
                last_movement = arduino_log
                break

        if last_movement:
            self.messenger.send_message(
                f'*Detected movement*\n'
                f'Current pir sensor: `{last_movement.pir_sensor}`\n'
                f'Timestamp: `{last_movement.received_at.strftime("%Y-%m-%d, %H:%M:%S")}`'
            )
            use_camera: bool = self.state[USE_CAMERA]

            if use_camera:
                updates: queue.Queue = self.state[UPDATES]
                updates.put(
                    MessengerUpdate(command=MessengerCommand(name=constants.BotCommands.CAMERA, args=('photo',))),
                )
