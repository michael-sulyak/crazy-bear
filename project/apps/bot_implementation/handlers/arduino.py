import datetime
import typing
from datetime import datetime, timedelta

import serial
from pandas import DataFrame

from .. import events
from ..constants import BotCommands, PHOTO, SECURITY_IS_ENABLED, USE_CAMERA
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ARDUINO_IS_ENABLED
from ...arduino.models import ArduinoLog
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ...common.utils import send_plot
from ...db import db_session
from ...messengers.base import BaseCommandHandler, Command


__all__ = (
    'Arduino',
)


class Arduino(BaseCommandHandler):
    support_commands = {
        BotCommands.ARDUINO,
        BotCommands.STATS,
    }
    _arduino_connector: typing.Optional[ArduinoConnector] = None

    def init_state(self) -> None:
        self.state.create_many(**{
            ARDUINO_IS_ENABLED: False,
        })

    def init_schedule(self) -> None:
        self.scheduler.every(1).hour.do(self._backup)

    def process_command(self, command: Command) -> None:
        if command.name == BotCommands.ARDUINO:
            if command.first_arg == ON:
                self._enable_arduino()
            elif command.first_arg == OFF:
                self._disable_arduino()
        elif command.name == BotCommands.STATS:
            self._show_stats(command)

    def update(self) -> None:
        if not self._arduino_connector:
            return

        if self._arduino_connector and not self._arduino_connector.is_active:
            self._disable_arduino()
            return

        self._process_arduino_updates()

    def clear(self) -> None:
        self._disable_arduino()

    def _enable_arduino(self) -> None:
        if self._arduino_connector:
            self.messenger.send_message('Arduino is already on')
            return

        self._arduino_connector = ArduinoConnector()

        try:
            self._arduino_connector.start()
        except serial.SerialException:
            self._arduino_connector = None
            self.state[ARDUINO_IS_ENABLED] = False
            self.messenger.send_message('Arduino can not be connected')
        else:
            self.state[ARDUINO_IS_ENABLED] = True
            self.messenger.send_message('Arduino is on')

    def _disable_arduino(self) -> None:
        self.state[ARDUINO_IS_ENABLED] = False

        db_session.query(ArduinoLog).delete()
        db_session.commit()

        if self._arduino_connector:
            self._arduino_connector.finish()
            self._arduino_connector = None
            self.messenger.send_message('Arduino is off')
        else:
            self.messenger.send_message('Arduino is already off')

    def _show_stats(self, command: Command) -> None:
        if not self.state[ARDUINO_IS_ENABLED]:
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
        if not self._arduino_connector:
            return

        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        new_arduino_logs = self._arduino_connector.process_updates()

        if not security_is_enabled or not new_arduino_logs:
            return

        last_movement = None

        for arduino_log in reversed(new_arduino_logs):
            if arduino_log.pir_sensor <= 1:
                continue

            if not last_movement or last_movement.pir_sensor < arduino_log.pir_sensor:
                last_movement = arduino_log

        if last_movement:
            events.motion_detected.send()

            self.messenger.send_message(
                f'*Detected movement*\n'
                f'Current pir sensor: `{last_movement.pir_sensor}`\n'
                f'Timestamp: `{last_movement.received_at.strftime("%Y-%m-%d, %H:%M:%S")}`'
            )
            use_camera: bool = self.state[USE_CAMERA]

            if use_camera:
                self._put_command(BotCommands.CAMERA, PHOTO)

    def _backup(self):
        if not self.state[ARDUINO_IS_ENABLED]:
            return

        all_logs = db_session.query(
            ArduinoLog.pir_sensor,
            ArduinoLog.humidity,
            ArduinoLog.temperature,
            ArduinoLog.received_at,
        ).order_by(
            ArduinoLog.received_at,
        ).all()

        if all_logs:
            df = DataFrame(all_logs, columns=('pir_sensor', 'humidity', 'temperature', 'received_at',))
            file_storage.upload_df_as_xlsx(
                file_name=f'arduino_logs/{df.iloc[0].received_at.strftime("%Y-%m-%d, %H:%M:%S")}'
                          f'-{df.iloc[-1].received_at.strftime("%Y-%m-%d, %H:%M:%S")}.xlsx',
                data_frame=df,
            )

        day_ago = datetime.today() - timedelta(days=1)
        db_session.query(ArduinoLog).filter(ArduinoLog.received_at <= day_ago).delete()
        db_session.commit()
