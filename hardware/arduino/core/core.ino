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

//const char typeSetSettings[] = "set_settings";
//const char typeGetSettings[] = "get_settings";
//const char typeSettings[] = "settings";
//const char typeSensors[] = "sensors";

const unsigned short sendingDelay = 10 * 1000;
const unsigned short detectionDelay = 1 * 1000;
unsigned long lastSentAt = 0;

StaticJsonDocument<64> jsonBuffer;

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

//     const int pirSensor = analogRead(PIR_SENSOR_PIN);
//     const unsigned short diff = millis() - lastSentAt;
//     const bool needToSend = (pirSensor > 20 && diff >= detectionDelay) || (diff >= sendingDelay);
//
//     if (needToSend) {
//       jsonBuffer["type"] = typeSensors;
//       jsonBuffer["payload"]["pir_sensor"] = pirSensor;
//       jsonBuffer["payload"]["humidity"] = dhtSensor.readHumidity();
//       jsonBuffer["payload"]["temperature"] = dhtSensor.readTemperature();
//       sendJsonBuffer();
//       jsonBuffer.clear();
//
//       lastSentAt = millis();
//     }

    if (radioManager.hasInputData()) {
        Serial.println("Has something");

        if (radioManager.read(jsonBuffer)) {
            Serial.println("Result:");
            serializeJson(jsonBuffer, Serial);
            Serial.println();
            Serial.println("----");
            jsonBuffer.clear();
        }
    }

    delay(200);
}

void sendJsonBuffer() {
    jsonBuffer["sent_at"] = millis();
    serializeJson(jsonBuffer, Serial);
    Serial.println();
}
