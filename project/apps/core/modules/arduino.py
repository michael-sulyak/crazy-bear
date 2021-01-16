import datetime
import io
import typing

import schedule
import serial
from pandas import DataFrame

from ..base import BaseModule, Command
from ..constants import ARDUINO_IS_ENABLED
from ...arduino.base import ArduinoConnector
from ...arduino.models import ArduinoLog
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ...common.utils import create_plot, single_synchronized, synchronized
from ...core import events
from ...core.constants import PHOTO, SECURITY_IS_ENABLED, USE_CAMERA
from ...db import db_session
from ...messengers.constants import BotCommands
from .... import config


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
            scheduler.every(1).hour.do(self.task_queue.push, self._backup),
        )

    def connect_to_events(self) -> None:
        super().connect_to_events()

        events.request_for_statistics.connect(self._create_arduino_sensor_stats)

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

    @synchronized
    def tick(self) -> None:
        if self._arduino_connector and not self._arduino_connector.is_active:
            self._disable_arduino()
            return

        if self._arduino_connector and self._arduino_connector.is_active:
            self.task_queue.push(self._process_arduino_updates)

    @synchronized
    def disconnect(self) -> None:
        super().disconnect()
        self._disable_arduino()

    @synchronized
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

    @synchronized
    def _disable_arduino(self) -> None:
        self.state[ARDUINO_IS_ENABLED] = False

        if self._arduino_connector:
            self._arduino_connector.finish()
            self._arduino_connector = None
            self.messenger.send_message('Arduino is off')
        else:
            self.messenger.send_message('Arduino is already off')

        self._backup()

        with db_session().transaction:
            db_session().query(ArduinoLog).delete()

    def _create_arduino_sensor_stats(self, command: Command) -> typing.Optional[typing.List[io.BytesIO]]:
        if not self.state[ARDUINO_IS_ENABLED]:
            return

        stats = ArduinoLog.get_avg(
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not stats:
            return None

        return [
            create_plot(title='PIR Sensor', x_attr='time', y_attr='pir_sensor', stats=stats),
            create_plot(title='Humidity', x_attr='time', y_attr='humidity', stats=stats),
            create_plot(title='Temperature', x_attr='time', y_attr='temperature', stats=stats),
        ]

    @single_synchronized
    def _process_arduino_updates(self) -> None:
        if not self._arduino_connector or not self._arduino_connector.is_active:
            return

        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        new_arduino_logs = self._arduino_connector.process_updates()

        if not new_arduino_logs:
            return

        if security_is_enabled:
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
                    self._run_command(BotCommands.CAMERA, PHOTO)

        events.new_arduino_logs.send(new_arduino_logs=new_arduino_logs)

    @single_synchronized
    def _backup(self):
        if not self.state[ARDUINO_IS_ENABLED]:
            return

        all_logs = db_session().query(
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

        timestamp = datetime.datetime.now() - config.STORAGE_TIME

        with db_session().transaction:
            db_session().query(ArduinoLog).filter(ArduinoLog.received_at <= timestamp).delete()
