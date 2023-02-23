class ArduinoResponseTypes:
    SENSORS = 'sensors'


class ArduinoSensorTypes:
    PIR_SENSOR = 'pir_sensor'
    HUMIDITY = 'humidity'
    TEMPERATURE = 'temperature'

    ALL = {
        PIR_SENSOR,
        HUMIDITY,
        TEMPERATURE,
    }


SENSORS_PAYLOAD_MAP = {
    'p': 'pir_sensor',
    'h': 'humidity',
    't': 'temperature',
}
