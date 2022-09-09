import datetime
import typing

import serial

from ..base import BaseModule, Command
from ..constants import ARDUINO_IS_ENABLED, BotCommands, MotionTypeSources
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ArduinoSensorTypes
from ...common import doc
from ...common.constants import OFF, ON
from ...common.utils import synchronized_method, with_throttling
from ...core import events
from ...core.constants import SECURITY_IS_ENABLED
from ...messengers.utils import escape_markdown
from ...signals.models import Signal
from ...task_queue import IntervalTask, TaskPriorities


__all__ = (
    'Arduino',
)


class Arduino(BaseModule):
    doc = doc.generate_doc(
        title='Arduino',
        commands=(
            doc.CommandDef(BotCommands.ARDUINO, doc.OptionsDef(ON, OFF)),
        ),
    )

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

        if self.state[ARDUINO_IS_ENABLED]:
            self._disable_arduino()

    @synchronized_method
    def _check_arduino_connector(self) -> None:
        if not self.state[ARDUINO_IS_ENABLED]:
            return

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
                self._send_message_about_movement(last_movement)
                events.motion_detected.send(source=MotionTypeSources.SENSORS)

    @synchronized_method
    @with_throttling(datetime.timedelta(seconds=5), count=1)
    def _send_message_about_movement(self, last_movement: Signal) -> None:
        self.messenger.send_message(
            (
                f'*Detected movement*\n'
                f'Current pir sensor: `{last_movement.value}`\n'
                f'Timestamp: `{escape_markdown(last_movement.received_at.strftime("%Y-%m-%d, %H:%M:%S"))}`'
            ),
            use_markdown=True,
        )
