import json
import logging
import typing
from dataclasses import dataclass, field
from datetime import datetime

import serial

from . import constants
from .models import ArduinoLog
from ..db import db_session
from ... import config


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
    def update_data_delay(cls, data_delay: int) -> 'ArduinoRequest':
        assert data_delay >= 0

        return cls(type=constants.ArduinoRequestTypes.UPDATE_SETTINGS, payload={'data_delay': data_delay})


class ArduinoConnector:
    is_active: bool = True
    TERMINATOR: bytes = b'\r\n'
    _serial: serial.Serial
    _buffer: bytes = b''
    _settings: dict

    def __init__(self, ser: typing.Optional[serial.Serial] = None) -> None:
        if ser is None:
            ser = serial.Serial()

        self._serial = ser
        self._settings = {}

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

    def process_updates(self) -> typing.List[ArduinoLog]:
        if not self.is_active:
            return []

        new_arduino_logs = []

        for response in self._read_serial():
            logging.debug(response)

            if response.type == constants.ArduinoResponseTypes.SENSORS:
                arduino_log = ArduinoLog(**response.payload, received_at=response.received_at)
                if not new_arduino_logs:
                    new_arduino_logs.append(arduino_log)
                elif new_arduino_logs[-1].pir_sensor < arduino_log.pir_sensor:
                    new_arduino_logs[-1] = arduino_log
            elif response.type == constants.ArduinoResponseTypes.SETTINGS:
                self._settings = response.payload

        if new_arduino_logs:
            with db_session().transaction:
                db_session().add_all(new_arduino_logs)

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

            if not isinstance(line, dict):
                continue

            yield ArduinoResponse(**line)
