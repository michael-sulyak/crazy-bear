import json
import logging
import typing
from dataclasses import dataclass, field
import datetime

import serial

from . import constants
from ..common.utils import current_time
from ..signals.models import Signal
from ... import config


@dataclass
class ArduinoResponse:
    type: str
    sent_at: int
    payload: typing.Optional[dict] = None
    received_at: datetime.datetime = field(default_factory=current_time)


# @dataclass
# class ArduinoRequest:
#     type: str
#     payload: typing.Optional[dict] = None
#
#     @classmethod
#     def request_settings(cls) -> 'ArduinoRequest':
#         return cls(type=constants.ArduinoRequestTypes.REQUEST_SETTINGS)
#
#     @classmethod
#     def update_data_delay(cls, data_delay: int) -> 'ArduinoRequest':
#         assert data_delay >= 0
#
#         return cls(type=constants.ArduinoRequestTypes.UPDATE_SETTINGS, payload={'data_delay': data_delay})


class ArduinoConnector:
    terminator: bytes = b'\r\n'
    is_active: bool = False
    _serial: serial.Serial
    _buffer: bytes = b''
    _settings: dict

    def __init__(self, ser: typing.Optional[serial.Serial] = None) -> None:
        if ser is None:
            ser = serial.Serial()
            ser.setPort(config.ARDUINO_TTY)

        self._serial = ser
        self._settings = {}

    def open(self) -> None:
        if self.is_active:
            return

        self._serial.close()

        try:
            self._serial.open()
            self._serial.reset_input_buffer()
        except Exception:
            self.close()
            raise

        self.is_active = True

    def process_updates(self) -> typing.List[Signal]:
        signals = []

        for response in self._read_serial():
            logging.debug(response)

            if response.type == constants.ArduinoResponseTypes.SENSORS:
                for name, value in response.payload.items():
                    signals.append(Signal(type=name, value=value, received_at=response.received_at))

            if response.type == constants.ArduinoResponseTypes.SETTINGS:
                self._settings = response.payload

        if signals:
            Signal.bulk_add(signals)

        return signals

    def close(self) -> None:
        self._serial.close()
        self.is_active = False

    def _read_serial(self) -> typing.Iterator[ArduinoResponse]:
        self._buffer += self._serial.read(self._serial.in_waiting)

        lines = []

        if self.terminator in self._buffer:
            lines = self._buffer.split(self.terminator)

            if lines[-1] != b'':
                self._buffer = lines[-1]

            lines = lines[:-1]

        for line in lines:
            try:
                line = line.decode()
                line = json.loads(line)
            except (json.decoder.JSONDecodeError, UnicodeDecodeError,) as e:
                logging.warning(e)
                continue

            if not isinstance(line, dict):
                continue

            yield ArduinoResponse(**line)
