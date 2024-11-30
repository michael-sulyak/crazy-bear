from ...signals.models import Signal
from ..base import ArduinoConnector
from ..constants import ArduinoSensorTypes


class TestMessenger:
    pass


class TestSerial:
    in_waiting: int = 0
    _is_open: bool = False
    _buffer: bytes = b''

    def open(self):
        self._is_open = True

    def close(self):
        self._is_open = False

    def reset_input_buffer(self):
        self.in_waiting = 0
        self._buffer = b''

    def read(self, size: int = 1):
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result

    def _write_message(self, data: bytes):
        self.in_waiting += len(data)
        self._buffer += data


def test_connection():
    ser = TestSerial()
    arduino_connector = ArduinoConnector(serial=ser)

    arduino_connector.open()
    assert ser._is_open is True

    arduino_connector.close()
    assert ser._is_open is False


def test_process_updates(test_db):
    ser = TestSerial()
    arduino_connector = ArduinoConnector(serial=ser)

    arduino_connector.open()
    assert ser._is_open is True

    ser._write_message(b'{"t":"sensors","p":{"p": 100,"h": 20,"t": 30}}' + arduino_connector._terminator)
    signals = arduino_connector.process_updates()
    Signal.bulk_add(signals)

    humidity = Signal.get_one_aggregated(ArduinoSensorTypes.HUMIDITY)
    temperature = Signal.get_one_aggregated(ArduinoSensorTypes.TEMPERATURE)
    pir_sensor = Signal.get_one_aggregated(ArduinoSensorTypes.PIR_SENSOR)

    assert pir_sensor == 100
    assert humidity == 20
    assert temperature == 30

    arduino_connector.close()
    assert ser._is_open is False
