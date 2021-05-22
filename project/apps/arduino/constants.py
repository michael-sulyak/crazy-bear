class ArduinoResponseTypes:
    SETTINGS = 'settings'
    SENSORS = 'sensors'


class ArduinoRequestTypes:
    REQUEST_SETTINGS = 'request_settings'
    UPDATE_SETTINGS = 'update_settings'


class ArduinoSensorTypes:
    PIR_SENSOR = 'pir_sensor'
    HUMIDITY = 'humidity'
    TEMPERATURE = 'temperature'

    ALL = {
        PIR_SENSOR,
        HUMIDITY,
        TEMPERATURE,
    }
