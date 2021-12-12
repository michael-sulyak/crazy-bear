#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// For radio
#include "radio_manager/radio_manager.cpp"
#include <RF24.h>  // https://nrf24.github.io/RF24/

// For crypto
#include <Crypto.h>  // https://rweather.github.io/arduinolibs/crypto.html
#include <AES.h>  // https://rweather.github.io/arduinolibs/crypto.html


#define PIN_CE 7
#define PIN_CSN 8
#define RADIO_ADDRESS 0xF0F0F0F066

#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2


RF24 radio(PIN_CE, PIN_CSN);
RadioManager radioManager(radio);


#define typeSetSettings "set_settings"
#define typeGetSettings "get_settings"
#define typeSettings "settings"
#define typeSensors "sensors"

const unsigned short sendingDelay = 10 * 1000;
const unsigned short detectionDelay = 1 * 1000;
const unsigned short radioDelay = 10 * 1000;
unsigned long lastSentAt = 0;
unsigned long lastRadioAt = 0;

StaticJsonDocument<MSG_SIZE> jsonBuffer;

DHT dhtSensor(DHT_SENSOR_PIN, DHT22);


void setup() {
    Serial.begin(9600);
    dhtSensor.begin();
    radioManager.initRadio();
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

        if (millis() - lastRadioAt >= lastRadioAt) {
            sendJsonBuffer();
            radioManager.send(jsonBuffer);
            lastRadioAt = millis();

            Serial.print("Available memory: ");
            Serial.print(availableMemory());
            Serial.println(" b.");
        }

        jsonBuffer.clear();

        lastSentAt = millis();
    }

    delay(200);
}

void sendJsonBuffer() {
    serializeJson(jsonBuffer, Serial);
    Serial.println();
}
