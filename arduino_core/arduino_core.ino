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

#define PIR_SENSOR_PIN A0
#define DHT_SENSOR_PIN 2



int availableMemory() {
  // Use 1024 with ATmega168
  int size = 2048;
  byte *buf;
  while ((buf = (byte *) malloc(--size)) == NULL);
  free(buf);
  return size;
}

class RadioManager {
#define BLOCK_SIZE 32
#define MSG_SIZE 64

  public:
    RadioManager(RF24 &radio) {
      _radio = &radio;
      _aes128 = new AES128;

      //      const uint8_t aue128_key[16] = AES128_KEY;
      //      _aes128->setKey(aue128_key, 16);
      //      delete[] aue128_key;
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

      Serial.println("-> 1");

      if (!_radio->write(&startedBytes, sizeof(startedBytes))) {
        return false;
      }
      delay(50);
      Serial.println("-> 2");

      char buffer[MSG_SIZE];
      serializeJson(jsonBuffer, buffer);
      //      _aes128->encryptBlock(buffer, buffer);

      for (int i = 0; i < MSG_SIZE; i += BLOCK_SIZE) {
        if (buffer[i] == '\0') {
          break;
        }
        Serial.print("-> 2 -> ");
        Serial.println(i);

        if (!_radio->write(&buffer[i], BLOCK_SIZE)) {
          return false;
        }

        delay(50);
      }
      Serial.println("-> 3");
      Serial.print("availableMemory=");
      Serial.println(availableMemory());


      Serial.println("-> 4");

      if (!_radio->write(&finishedBytes, sizeof(finishedBytes))) {
        Serial.println("-> 4.5");
        return false;
      }
      Serial.println("-> 5");

      _radio->startListening();
      Serial.println("-> 6");


      return true;
    }

    bool read(StaticJsonDocument<MSG_SIZE>& jsonBuffer) {
      char buffer[MSG_SIZE];
      char blockBuffer[BLOCK_SIZE];

      _radio->read(&blockBuffer, BLOCK_SIZE);

      Serial.print("Read: ");
      Serial.println(blockBuffer);

      Serial.println("-> 1");

      if (strcmp(blockBuffer, startedBytes) != 0) {
        Serial.println("-> 2");
        return false;
      }

      unsigned long startGettingAt = millis();

      unsigned short int part = 0;

      while (millis() - startGettingAt < 2000) {
        if (!_radio->available()) {
          delay(20);
          continue;
        }

        _radio->read(&blockBuffer, BLOCK_SIZE);
        Serial.print("Read: ");
        Serial.println(blockBuffer);

        if (strcmp(blockBuffer, startedBytes) == 0) {
          Serial.println("-> 3");
          buffer[0] = '\0';
          part = 0;
          startGettingAt = millis();
          continue;
        }

        if (strcmp(blockBuffer, finishedBytes) == 0) {
          Serial.println("-> 4");
          deserializeJson(jsonBuffer, buffer);
          return true;
        }

        Serial.println("-> 5");

        strncpy(buffer + part, blockBuffer, BLOCK_SIZE);
        Serial.print("Part: ");
        Serial.println(part);
        part += BLOCK_SIZE - 1;
        Serial.print("Buffer: ");
        Serial.println(buffer);

        startGettingAt = millis();
      }

      Serial.println("-> 6");
      return false;
    }


    bool hasInputData() {
      return _radio->available();
    }

  private:
    RF24 *_radio;
    AES128 *_aes128;
    const char startedBytes[14] = "#~~~START~~~#";
    const char finishedBytes[11] = "#~~~END~~~#";
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

const unsigned short sendingDelay = 10 * 1000;
const unsigned short detectionDelay = 1 * 1000;
unsigned long lastSentAt = 0;

StaticJsonDocument<64> jsonBuffer;

DHT dhtSensor(DHT_SENSOR_PIN, DHT22);


void setup() {
  Serial.begin(9600);
  dhtSensor.begin();
  radioManager.initRadio();
//  Serial.println("Starting...");
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
    const unsigned short diff = millis() - lastSentAt;
    const bool needToSend = (pirSensor > 20 && diff >= detectionDelay) || (diff >= sendingDelay);
  
    if (needToSend) {
      jsonBuffer["type"] = typeSensors;
      jsonBuffer["payload"]["pir_sensor"] = pirSensor;
      jsonBuffer["payload"]["humidity"] = dhtSensor.readHumidity();
      jsonBuffer["payload"]["temperature"] = dhtSensor.readTemperature();
      sendJsonBuffer();
      jsonBuffer.clear();
  
      lastSentAt = millis();
    }

//  if (radio.available()) {
//    Serial.println("Has something");
//    char arr1[64];
//    radioManager.read(jsonBuffer);
//    serializeJson(jsonBuffer, Serial);
//    Serial.println();
//    jsonBuffer.clear();
//  }

  delay(200);
}

void rawRadioRead() {
  char buffer[64];
  radio.read(&buffer, 64);
  Serial.print("\"");
  Serial.print(buffer);
  Serial.println("\"");
  Serial.println(byte(buffer[0]));
}

void sendJsonBuffer() {
  jsonBuffer["sent_at"] = millis();
  serializeJson(jsonBuffer, Serial);
  Serial.println();
}
