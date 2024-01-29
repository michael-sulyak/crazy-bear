#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// Other pins:
#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2

// Vars:
#define TYPE_SET_SETTINGS "set_settings"
#define TYPE_GET_SETTINGS "get_settings"
#define TYPE_SETTINGS "settings"
#define TYPE_SENSORS "sensors"

// Global objects:
const unsigned int msgSize = 32 * 2;
StaticJsonDocument<msgSize> jsonBuffer;
DHT dhtSensor(DHT_SENSOR_PIN, DHT22);

// Global state:
struct {
    const unsigned long sendingDelay = 60000;
    const unsigned long detectionDelay = 1000;
    unsigned long lastSentAt = 0;
    bool debugMode = false;
} globalState;


void setup() {
    Serial.begin(9600);
    dhtSensor.begin();
    delay(1000);  // To warm up
}

void loop() {
    checkSerialInput();

    const int pirSensor = analogRead(PIR_SENSOR_PIN);
    const unsigned long diff = millis() - globalState.lastSentAt;
    const bool needToSendViaSerial = (pirSensor > 20 && diff >= globalState.detectionDelay) || (diff >= globalState.sendingDelay);

    if (needToSendViaSerial) {
        jsonBuffer["t"] = TYPE_SENSORS;
        jsonBuffer["p"]["p"] = pirSensor;
        jsonBuffer["p"]["h"] = dhtSensor.readHumidity();
        jsonBuffer["p"]["t"] = dhtSensor.readTemperature();

        if (needToSendViaSerial) {
            sendJsonBufferViaSerial();
            globalState.lastSentAt = millis();
        }

        jsonBuffer.clear();
    }

    delay(200);
}

void checkSerialInput() {
    if (!Serial.available()) {
        return;
    }

    String input = Serial.readString();
    input.trim();

    if (input == "debug=on") {
        globalState.debugMode = true;
        Serial.println("Debug enabled.");
    } else if (input == "debug=off") {
        globalState.debugMode = false;
        Serial.println("Debug disabled.");
    } else {
        Serial.println("Unknown command.");
    }
}

void sendJsonBufferViaSerial() {
    serializeJson(jsonBuffer, Serial);
    Serial.println();
}
