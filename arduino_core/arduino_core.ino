#include <DHT_U.h>  // https://github.com/adafruit/DHT-sensor-library
#include <DHT.h>  // https://github.com/adafruit/DHT-sensor-library
#include <ArduinoJson.h>  // https://arduinojson.org/

// For radio
#include <SPI.h>
#include <nRF24L01.h>  // https://nrf24.github.io/RF24/
#include <RF24.h>  // https://nrf24.github.io/RF24/

// For crypto

#include <Crypto.h>  // https://rweather.github.io/arduinolibs/crypto.html
#include <AES.h>  // https://rweather.github.io/arduinolibs/crypto.html

#define AES128_KEY {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F}


#define PIN_CE 7
#define PIN_CSN 8
#define RADIO_ADDRESS 0xF0F0F0F066
#define RADIO_ADDRESS 0xF0F0F0F066

#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2


class RadioManager {
  #define BLOCK_SIZE 32
  #define MSG_SIZE 64
  
  public:
    RadioManager(RF24 &radio) {
      _radio = &radio;
      _aes128 = new AES128;
      
      const byte aue128_key[16] = AES128_KEY;
      _aes128->setKey(aue128_key, 16);
      delete[] aue128_key;
    }
  
    void initRadio() {
      _radio->begin();
      _radio->setChannel(115);
      _radio->setDataRate(RF24_250KBPS);
      _radio->setPALevel(RF24_PA_MIN);
      _radio->openReadingPipe(0, RADIO_ADDRESS);
      _radio->setAutoAck(true);
      _radio->startListening();
    }

    bool send(StaticJsonDocument<MSG_SIZE>& jsonBuffer) {
      _radio->stopListening();
      
      if (!_radio->write(&startedBytes, sizeof(startedBytes))) {
        return false;
      }

      char buffer[MSG_SIZE];
      serializeJson(jsonBuffer, buffer);
//      _aes128->encryptBlock(buffer, buffer);

      for (int i = 0; i < MSG_SIZE; i += BLOCK_SIZE) {
        if (!_radio->write(&buffer[i], BLOCK_SIZE)) {
          return false;
        }
      }

      delete[] buffer;
   
      if (!_radio->write(&finishedBytes, sizeof(finishedBytes))) {
        return false;
      }
      
      _radio->startListening();

      return true;
    }

    bool read(StaticJsonDocument<MSG_SIZE>& jsonBuffer) {
      char buffer[MSG_SIZE];
      
      _radio->read(&buffer, MSG_SIZE);

      if (buffer != startedBytes) {
        return false;
      }

      unsigned long startGettingAt = millis();
      
      while (millis() - startGettingAt < 2000) {
        if (!_radio->available()) {
          delay(10);
          continue;
        }

        _radio->read(&buffer, BLOCK_SIZE);
        
        if (buffer == startedBytes) {
          continue;
        }

        if (buffer == finishedBytes) {
          deserializeJson(jsonBuffer, buffer);
          delete[] buffer;
          return true;
        }

        startGettingAt = millis();
      }

      delete[] buffer;
      return false;
    }

    
    bool hasInputData() {
      return _radio->available();
    }
  
  private:
    RF24 *_radio;
    AES128 *_aes128;
    static const byte startedBytes[14] = "#~~~START~~~#";
    static const byte finishedBytes[11] = "#~~~END~~~#";
};


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

int dataDelay = 10 * 1000;
int pirSensor;
unsigned long lastSentAt = 0;

StaticJsonDocument<64> jsonBuffer;

DHT dhtSensor(DHT_SENSOR_PIN, DHT22);


void setup() {
  Serial.begin(9600);
  dhtSensor.begin();
  radioManager.initRadio();
}

void loop() {
//  if (Serial.available() > 0) {
//    deserializeJson(jsonBuffer, Serial);
//
//    if (jsonBuffer["type"] == typeSetSettings) {
//        dataDelay = jsonBuffer["payload"]["data_delay"];
//    } else if (jsonBuffer["type"] == typeGetSettings) {
//        jsonBuffer.clear();
//        jsonBuffer["type"] = typeSettings;
//        jsonBuffer["payload"]["data_delay"] = dataDelay;
//        sendJsonBuffer();
//    }
//
//    jsonBuffer.clear();
//  }
//
//  pirSensor = analogRead(PIR_SENSOR_PIN);
//
//  if (pirSensor > 20 || millis() - lastSentAt >= dataDelay) {
//    jsonBuffer["type"] = typeSensors;
//    jsonBuffer["payload"]["pir_sensor"] = pirSensor;
//    jsonBuffer["payload"]["humidity"] = dhtSensor.readHumidity();
//    jsonBuffer["payload"]["temperature"] = dhtSensor.readTemperature();
//    sendJsonBuffer();
//    jsonBuffer.clear();
//    
//    lastSentAt = millis();
//  }

  if (radio.available()) {
    Serial.println("Has something");
    char arr1[32];
    //deserializeJson(jsonBuffer, radioForArduinoJson);
    //serializeJson(jsonBuffer, Serial);
    radio.read(&arr1, 32);
    Serial.println(arr1);
    jsonBuffer.clear();
  }

  delay(200);
}


void sendJsonBuffer() {
  jsonBuffer["sent_at"] = millis();
  serializeJson(jsonBuffer, Serial);
  Serial.println();
}
