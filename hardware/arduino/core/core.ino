#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// For radio
#include "radio_transmitter/radio_transmitter.cpp"


#define PIN_CE 7
#define PIN_CSN 8

#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2


RF24 radio(PIN_CE, PIN_CSN);
RadioTransmitter radioTransmitter(radio);


#define typeSetSettings "set_settings"
#define typeGetSettings "get_settings"
#define typeSettings "settings"
#define typeSensors "sensors"

const unsigned short sendingDelay = 10 * 1000;
const unsigned short detectionDelay = 1 * 1000;
const unsigned short radioDelay = 20 * 1000;
unsigned long lastSentAt = 0;
unsigned long lastRadioAt = 0;

bool isSilentMode = true;
bool isSilentModeInViewer = false;

StaticJsonDocument<MSG_SIZE> jsonBuffer;

DHT dhtSensor(DHT_SENSOR_PIN, DHT22);


void setup() {
    Serial.begin(9600);
    dhtSensor.begin();
    radioTransmitter.init();
}

void loop() {
//     if (Serial.available() > 0) {
//       deserializeJson(jsonBuffer, Serial);
//
//       if (jsonBuffer["type"] == typeSetSettings) {
//           sendingDelay = jsonBuffer["payload"]["data_delay"];
//       } else if (jsonBuffer["type"] == typeGetSettings) {
//           jsonBuffer.clear();
//           jsonBuffer["type"] = typeSettings;
//           jsonBuffer["payload"]["data_delay"] = sendingDelay;
//           sendJsonBuffer();
//       }
//
//       jsonBuffer.clear();
//     }

    const int pirSensor = analogRead(PIR_SENSOR_PIN);
    const unsigned long diff = millis() - lastSentAt;
    const bool needToSend = (pirSensor > 20 && diff >= detectionDelay) || (diff >= sendingDelay);

    if (needToSend) {
        jsonBuffer["t"] = typeSensors;
        jsonBuffer["p"]["p"] = pirSensor;
        jsonBuffer["p"]["h"] = dhtSensor.readHumidity();
        jsonBuffer["p"]["t"] = dhtSensor.readTemperature();
        sendJsonBuffer();

        if (millis() - lastRadioAt >= radioDelay) {
            radioTransmitter.powerUp();
            radioTransmitter.send(jsonBuffer);
            radioTransmitter.powerDown();
            lastRadioAt = millis();

//            Serial.print("Available memory: ");
//            Serial.print(availableMemory());
//            Serial.println("b");
        }

        jsonBuffer.clear();

        lastSentAt = millis();
    }

//    if (isSilentMode && !isSilentModeInViewer) {
//        isSilentModeInViewer = turnOnSilentModeForViewer();
//
//        if (isSilentModeInViewer) {
//            isSilentModeInViewer = !pingViewer();
//        }
//    }
//
//    if (!isSilentMode && isSilentModeInViewer) {
//        isSilentModeInViewer = !turnOffSilentModeForViewer();
//
//        if (!isSilentModeInViewer) {
//            isSilentModeInViewer = pingViewer();
//        }
//    }

    delay(200);
}

void sendJsonBuffer() {
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