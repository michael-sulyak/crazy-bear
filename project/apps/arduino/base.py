import datetime
import json
import logging
import typing
from dataclasses import dataclass, field

import serial as serial_lib

from libs.casual_utils.time import get_current_time
from . import constants
from ..signals.models import Signal
from ... import config


@dataclass
class ArduinoResponse:
    type: str
    payload: typing.Optional[dict] = None
    received_at: datetime.datetime = field(
        default_factory=get_current_time,
    )


class ArduinoConnector:
    is_active: bool = False
    _terminator: bytes = b'\r\n'
    _serial: serial_lib.Serial
    _empty_string: bytes = b''
    _buffer: bytes = _empty_string

    def __init__(self, serial: typing.Optional[serial_lib.Serial] = None) -> None:
        if serial is None:
            serial = serial_lib.Serial()
            serial.setPort(config.ARDUINO_TTY)

        self._serial = serial

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
                    if value is None:
                        # Skip, if we can't get data.
                        continue

                    signals.append(Signal(type=name, value=value, received_at=response.received_at))

        return signals

    def close(self) -> None:
        self._serial.close()
        self.is_active = False

    def _read_serial(self) -> typing.Iterator[ArduinoResponse]:
        self._buffer += self._serial.read(self._serial.in_waiting)

        lines = []

        if self._terminator in self._buffer:
            lines = self._buffer.split(self._terminator)

            if lines[-1] == self._empty_string:
                self._buffer = self._empty_string
            else:
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

            yield ArduinoResponse(
                type=line['t'],
                payload={
                    constants.SENSORS_PAYLOAD_MAP[key]: value
                    for key, value in line['p'].items()
                },
            )
