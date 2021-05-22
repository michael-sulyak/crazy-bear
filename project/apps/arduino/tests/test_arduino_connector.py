from ..base import ArduinoConnector
from ..constants import ArduinoSensorTypes
from ...signals.models import Signal


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
    arduino_connector = ArduinoConnector(ser=ser)

    arduino_connector.start()
    assert ser._is_open is True

    arduino_connector.finish()
    assert ser._is_open is False


def test_process_updates(test_db):
    ser = TestSerial()
    arduino_connector = ArduinoConnector(ser=ser)

    arduino_connector.start()
    assert ser._is_open is True

    ser._write_message(
        b'{"type": "sensors", "sent_at": 0, '
        b'"payload": {"pir_sensor": 100, "humidity": 20, "temperature": 30}}' + arduino_connector.TERMINATOR
    )
    arduino_connector.process_updates()

    humidity = Signal.last_aggregated(ArduinoSensorTypes.HUMIDITY)
    temperature = Signal.last_aggregated(ArduinoSensorTypes.TEMPERATURE)
    pir_sensor = Signal.last_aggregated(ArduinoSensorTypes.PIR_SENSOR)

    assert pir_sensor == 100
    assert humidity == 20
    assert temperature == 30

    arduino_connector.finish()
    assert ser._is_open is False
