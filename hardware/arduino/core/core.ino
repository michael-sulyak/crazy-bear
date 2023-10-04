#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// For radio:
#include "JsonRadioTransmitter/JsonRadioTransmitter.cpp"

// Pins for radio:
#define PIN_CE 10
#define PIN_CSN 9

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
const unsigned int msgSize = 32 * 2;
RadioTransmitter<StaticJsonDocument<msgSize>> radioTransmitter(radio, "root", "viewer", 88);
StaticJsonDocument<msgSize> jsonBuffer;
DHT dhtSensor(DHT_SENSOR_PIN, DHT22);

// Global state:
struct {
    const unsigned long sendingDelay = 60000;
    const unsigned long detectionDelay = 1000;
    const unsigned long radioDelay = 1000;
    unsigned long lastSentAt = 0;
    unsigned long lastRadioAt = 0;

//     bool isSilentMode = true;
//     bool isSilentModeInViewer = false;
    bool debugMode = false;
} globalState;


void setup() {
    Serial.begin(9600);
    dhtSensor.begin();
    radioTransmitter.init();
    delay(1000);  // To warm up
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

    const int pirSensor = analogRead(PIR_SENSOR_PIN);
    const unsigned long diff = millis() - globalState.lastSentAt;
    const bool needToSendViaSerial = (pirSensor > 20 && diff >= globalState.detectionDelay) || (diff >= globalState.sendingDelay);
    const bool needToSendViaRadio = millis() - globalState.lastRadioAt >= globalState.radioDelay;

    if (needToSendViaSerial || needToSendViaRadio) {
        jsonBuffer["t"] = TYPE_SENSORS;
        jsonBuffer["p"]["p"] = pirSensor;
        jsonBuffer["p"]["h"] = dhtSensor.readHumidity();
        jsonBuffer["p"]["t"] = dhtSensor.readTemperature();

        if (needToSendViaSerial) {
            sendJsonBufferViaSerial();
            globalState.lastSentAt = millis();
        }

        if (needToSendViaRadio) {
            radioTransmitter.powerUp();

            if (radioTransmitter.write(jsonBuffer)) {
                globalState.lastRadioAt = millis();
            }

            radioTransmitter.powerDown();
        }

        jsonBuffer.clear();
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
    if (!Serial.available()) {
        return;
    }

    String input = Serial.readString();
    input.trim();

    if (input == "debug=on") {
        globalState.debugMode = true;
        radioTransmitter.debugMode = true;
        Serial.println("Debug enabled.");
    } else if (input == "debug=off") {
        globalState.debugMode = false;
        radioTransmitter.debugMode = false;
        Serial.println("Debug disabled.");
    } else {
        Serial.println("Unknown command.");
    }
}

void sendJsonBufferViaSerial() {
    serializeJson(jsonBuffer, Serial);
    Serial.println();
}

// bool pingViewer() {
//     radioTransmitter.powerUp();
//     const bool result = radioTransmitter.ping();
//     radioTransmitter.powerDown();
//     return result;
// }

// bool turnOnSilentModeForViewer() {
//     jsonBuffer["t"] = "sm";
//     jsonBuffer["v"] = "on";
//     jsonBuffer["s"] = 1;
//
//     radioTransmitter.powerUp();
//     const bool result = radioTransmitter.write(jsonBuffer);
//     radioTransmitter.powerDown();
//
//     jsonBuffer.clear();
//
//     return result;
// }

// bool turnOffSilentModeForViewer() {
//     jsonBuffer["t"] = "sm";
//     jsonBuffer["v"] = "on";
//
//     radioTransmitter.powerUp();
//     const bool result = radioTransmitter.write(jsonBuffer) || radioTransmitter.write(jsonBuffer);
//     radioTransmitter.powerDown();
//
//     jsonBuffer.clear();
//
//     return result;
// }
