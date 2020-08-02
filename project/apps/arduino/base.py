import json
import logging
import typing
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import serial
from pandas import DataFrame

from . import constants
from .models import ArduinoLog
from ..common.storage import file_storage
from ..db import db_session
from ... import config


# ArduinoSensorsData = namedtuple(
#     typename='ArduinoSensorsData',
#     field_names=(
#         'pir_sensor',
#         'humidity',
#         'temperature',
#         'received_at',
#     ),
# )


@dataclass
class ArduinoResponse:
    type: str
    sent_at: int
    payload: typing.Optional[dict] = None
    received_at: datetime = field(default_factory=datetime.now)


@dataclass
class ArduinoRequest:
    type: str
    payload: typing.Optional[dict] = None

    @classmethod
    def request_settings(cls) -> 'ArduinoRequest':
        return cls(type=constants.ArduinoRequestTypes.REQUEST_SETTINGS)

    @classmethod
    def update_ttl(cls, ttl: int) -> 'ArduinoRequest':
        return cls(type=constants.ArduinoRequestTypes.UPDATE_SETTINGS, payload={'ttl': ttl})


class ArduinoConnector:
    is_active: bool = True
    TERMINATOR: bytes = b'\r\n'
    _serial: serial.Serial
    _buffer: bytes = b''
    _settings: dict
    _last_clear_at: datetime

    def __init__(self, ser: typing.Optional[serial.Serial] = None) -> None:
        if ser is None:
            ser = serial.Serial()

        self._serial = ser
        self._settings = {}
        self._last_clear_at = datetime.now()

    def start(self) -> None:
        self.is_active = True
        self._serial.close()
        self._serial.port = config.ARDUINO_TTY

        try:
            self._serial.open()
            self._serial.reset_input_buffer()
        except Exception:
            self.finish()
            raise

    # def process_updates(self) -> typing.List[Signal]:
    #     if not self.is_active:
    #         return []
    #
    #     new_signals = []
    #
    #     for response in self._read_serial():
    #         logging.debug(response)
    #
    #         if response.type == ArduinoResponseTypes.SENSORS:
    #             arduino_sensors_data = ArduinoSensorsData(**response.payload)
    #
    #             new_signals.extend((
    #                 Signal(
    #                     type=ArduinoSensorTypes.PIR_SENSOR,
    #                     value=arduino_sensors_data.pir_sensor,
    #                     received_at=response.received_at,
    #                 ),
    #                 Signal(
    #                     type=ArduinoSensorTypes.HUMIDITY,
    #                     value=arduino_sensors_data.humidity,
    #                     received_at=response.received_at,
    #                 ),
    #                 Signal(
    #                     type=ArduinoSensorTypes.TEMPERATURE,
    #                     value=arduino_sensors_data.temperature,
    #                     received_at=response.received_at,
    #                 ),
    #             ))
    #         elif response.type == ArduinoResponseTypes.SETTINGS:
    #             self._settings = response.payload
    #         else:
    #             raise Exception(f'Data type {response.type} is not support.')
    #
    #     if new_signals:
    #         db_session.add_all(new_signals)
    #         db_session.commit()
    #         now = datetime.now()
    #
    #         if now - self._last_clear_at >= timedelta(hours=1):
    #             self._last_clear_at = now
    #             self._backup()
    #
    #     return new_signals

    def process_updates(self) -> typing.List[ArduinoLog]:
        if not self.is_active:
            return []

        new_arduino_logs = []

        for response in self._read_serial():
            logging.debug(response)

            if response.type == constants.ArduinoResponseTypes.SENSORS:
                arduino_log = ArduinoLog(**response.payload, received_at=response.received_at)
                new_arduino_logs.append(arduino_log)
            elif response.type == constants.ArduinoResponseTypes.SETTINGS:
                self._settings = response.payload

        if new_arduino_logs:
            db_session.add_all(new_arduino_logs)
            db_session.commit()
            now = datetime.now()

            if now - self._last_clear_at >= timedelta(hours=1):
                self._last_clear_at = now
                self._backup()

        return new_arduino_logs

    def finish(self) -> None:
        self.is_active = False
        self._serial.close()

    def _read_serial(self) -> typing.Iterator[ArduinoResponse]:
        self._buffer += self._serial.read(self._serial.in_waiting)
        lines = []

        if self.TERMINATOR in self._buffer:
            lines = self._buffer.split(self.TERMINATOR)
            self._buffer = lines[-1]

        for line in lines[:-1]:
            if not line:
                continue

            try:
                line = line.decode()
                line = json.loads(line)
            except (json.decoder.JSONDecodeError, UnicodeDecodeError,) as e:
                logging.warning(e)
                continue

            yield ArduinoResponse(**line)

    @staticmethod
    def _backup():
        all_logs = db_session.query(
            ArduinoLog.pir_sensor,
            ArduinoLog.humidity,
            ArduinoLog.temperature,
            ArduinoLog.received_at,
        ).order_by(
            ArduinoLog.received_at,
        ).all()

        if all_logs:
            # df = DataFrame(all_logs, columns=('id', 'pir_sensor', 'humidity', 'temperature', 'received_at',))
            # df.set_index('id', inplace=True)
            df = DataFrame(all_logs, columns=('pir_sensor', 'humidity', 'temperature', 'received_at',))
            file_storage.upload_df_as_xlsx(
                file_name=f'arduino_logs/{df.iloc[0].received_at.strftime("%Y-%m-%d, %H:%M:%S")}'
                          f'-{df.iloc[-1].received_at.strftime("%Y-%m-%d, %H:%M:%S")}.xlsx',
                data_frame=df,
            )

        day_ago = datetime.today() - timedelta(days=1)
        db_session.query(ArduinoLog).filter(ArduinoLog.received_at <= day_ago).delete()
        db_session.commit()
