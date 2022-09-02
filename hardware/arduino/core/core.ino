#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// For radio:
#include "radio_transmitter/radio_transmitter.cpp"

// Pins for radio:
#define PIN_CE 7
#define PIN_CSN 8

// Other pins:
#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2

// Vars:
#define TYPE_SET_SETTINGS "set_settings"
#define TYPE_GET_SETTINGS "get_settings"
#define TYPE_SETTINGS "settings"
#define TYPE_SENSORS "sensors"

// Global objects:
RF24 radio(PIN_CE, PIN_CSN);
RadioTransmitter radioTransmitter(radio);
StaticJsonDocument<MSG_SIZE> jsonBuffer;
DHT dhtSensor(DHT_SENSOR_PIN, DHT22);

// Global state:
struct {
    const unsigned short sendingDelay = 10 * 1000;
    const unsigned short detectionDelay = 1 * 1000;
    const unsigned short radioDelay = 20 * 1000;
    unsigned long lastSentAt = 0;
    unsigned long lastRadioAt = 0;

    bool isSilentMode = true;
    bool isSilentModeInViewer = false;
    bool isDebugMode = false;
} globalState;


void setup() {
    Serial.begin(9600);
    dhtSensor.begin();
    radioTransmitter.init();
}

void loop() {
//     if (Serial.available() > 0) {
//       deserializeJson(jsonBuffer, Serial);
//
//       if (jsonBuffer["type"] == TYPE_SET_SETTINGS) {
//           globalState.sendingDelay = jsonBuffer["payload"]["data_delay"];
//       } else if (jsonBuffer["type"] == TYPE_GET_SETTINGS) {
//           jsonBuffer.clear();
//           jsonBuffer["type"] = TYPE_SETTINGS;
//           jsonBuffer["payload"]["data_delay"] = globalState.sendingDelay;
//           sendJsonBufferViaSerial();
//       }
//
//       jsonBuffer.clear();
//     }
    checkSerialInput();

    const unsigned short pirSensor = analogRead(PIR_SENSOR_PIN);
    const unsigned long diff = millis() - globalState.lastSentAt;
    const bool needToSend = (pirSensor > 20 && diff >= globalState.detectionDelay) || (diff >= globalState.sendingDelay);

    if (needToSend) {
        jsonBuffer["t"] = TYPE_SENSORS;
        jsonBuffer["p"]["p"] = pirSensor;
        jsonBuffer["p"]["h"] = dhtSensor.readHumidity();
        jsonBuffer["p"]["t"] = dhtSensor.readTemperature();
        sendJsonBufferViaSerial();

        if (millis() - globalState.lastRadioAt >= globalState.radioDelay) {
            radioTransmitter.powerUp();
            radioTransmitter.send(jsonBuffer);
            radioTransmitter.powerDown();
            globalState.lastRadioAt = millis();

            if (globalState.isDebugMode) {
               Serial.print("Available memory: ");
               Serial.print(availableMemory());
               Serial.println("b");
            }
        }

        jsonBuffer.clear();

        globalState.lastSentAt = millis();
    }

//    if (globalState.isSilentMode && !globalState.isSilentModeInViewer) {
//        globalState.isSilentModeInViewer = turnOnSilentModeForViewer();
//
//        if (globalState.isSilentModeInViewer) {
//            globalState.isSilentModeInViewer = !pingViewer();
//        }
//    }
//
//    if (!globalState.isSilentMode && globalState.isSilentModeInViewer) {
//        globalState.isSilentModeInViewer = !turnOffSilentModeForViewer();
//
//        if (!globalState.isSilentModeInViewer) {
//            globalState.isSilentModeInViewer = pingViewer();
//        }
//    }

    delay(200);
}

void checkSerialInput() {
    if (Serial.available() == 0) {
        return;
    }

    String input = Serial.readString();
    input.trim();

    if (input == "debug=on") {
        globalState.isDebugMode = true;
        radioTransmitter.isDebugMode = true;
        Serial.println("Debug enabled.");
    } else if (input == "debug=off") {
        globalState.isDebugMode = false;
        radioTransmitter.isDebugMode = false;
        Serial.println("Debug disabled.");
    } else {
        Serial.println("Unknown command.");
    }
}

void sendJsonBufferViaSerial() {
    serializeJson(jsonBuffer, Serial);
    Serial.println();
}

bool pingViewer() {
    radioTransmitter.powerUp();
    const bool result = radioTransmitter.ping();
    radioTransmitter.powerDown();
    return result;
}

bool turnOnSilentModeForViewer() {
    jsonBuffer["t"] = "sm";
    jsonBuffer["v"] = "on";
    jsonBuffer["s"] = 1;

    radioTransmitter.powerUp();
    const bool result = radioTransmitter.send(jsonBuffer);
    radioTransmitter.powerDown();

    jsonBuffer.clear();

    return result;
}

bool turnOffSilentModeForViewer() {
    jsonBuffer["t"] = "sm";
    jsonBuffer["v"] = "on";

    radioTransmitter.powerUp();
    const bool result = radioTransmitter.send(jsonBuffer);
    radioTransmitter.powerDown();

    jsonBuffer.clear();

    return result;
}
