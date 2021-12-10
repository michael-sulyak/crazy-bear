#include "radio_manager.hh"

#include <ArduinoJson.h>

// For radio
#include <SPI.h>
#include <nRF24L01.h>  // https://nrf24.github.io/RF24/
#include <RF24.h>  // https://nrf24.github.io/RF24/

// For crypto
#include <Crypto.h>  // https://rweather.github.io/arduinolibs/crypto.html
#include <AES.h>  // https://rweather.github.io/arduinolibs/crypto.html

#define RADIO_ADDRESS 0xF0F0F0F066
#define MSG_DELAY 50
#define AES128_KEY {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F}
#define ENCRYPT false
#define DEBUG true

#if ENCRYPT
const uint8_t aue128_key[16] = AES128_KEY;
#endif

void rawRadioRead(RF24 &radio) {
    char buffer[33];
    radio.read(&buffer, 32);
    buffer[32] = '\0';
    Serial.print("`");
    Serial.print(buffer);
    Serial.println("`");
    Serial.println(byte(buffer[0]));
}

int availableMemory() {
    // Use 1024 with ATmega168
    int size = 2048;
    byte *buf;
    while ((buf = (byte *) malloc(--size)) == NULL);
    free(buf);
    return size;
}

RadioManager::RadioManager(RF24 &radio) {
    _radio = &radio;
    _aes128 = new AES128;
}

void RadioManager::initRadio() {
    _radio->begin();
    _radio->setChannel(115);
    _radio->setDataRate(RF24_250KBPS);
    _radio->setPALevel(RF24_PA_MIN);
    _radio->openWritingPipe(RADIO_ADDRESS);
    _radio->openReadingPipe(0, RADIO_ADDRESS);
    _radio->setAutoAck(true);
    _radio->startListening();
}

bool RadioManager::send(StaticJsonDocument<MSG_SIZE> &jsonBuffer) {
    _radio->stopListening();

#if DEBUG
    Serial.println("Start sending...");
#endif

    if (!_radio->write(&startedBytes, sizeof(startedBytes))) {
#if DEBUG
        Serial.println("Not delivered.");
#endif
        return false;
    }

    delay(MSG_DELAY);

#if DEBUG
    Serial.println("Serializing JSON...");
#endif

    char buffer[MSG_SIZE];
    serializeJson(jsonBuffer, buffer);

#if ENCRYPT
#if DEBUG
    Serial.println("Start encryption...");
#endif
    for (unsigned int i = 0; i < MSG_SIZE; i += _aes128->blockSize()) {
        _aes128->clear();
        _aes128->setKey(aue128_key, _aes128->keySize());
        _aes128->encryptBlock(&buffer[i], &buffer[i]);
    }
#endif

#if DEBUG
    Serial.print("Buffer for sending: ");
    Serial.println(buffer);
#endif

    for (unsigned int i = 0; i < MSG_SIZE; i += BLOCK_SIZE) {
//        bool isLastBlock = false;
//
//        for (unsigned int j = i; j < i + BLOCK_SIZE; ++j) {
//            if (buffer[j] == '\0') {
//                isLastBlock = true;
//                break;
//            }
//        }

#if DEBUG
        Serial.print("Block for process:");
        Serial.println(i / BLOCK_SIZE + 1);
#endif

        if (!_radio->write(&buffer[i], BLOCK_SIZE)) {
#if DEBUG
            Serial.println("Not delivered.");
#endif
            return false;
        }

        delay(MSG_DELAY);

//        if (isLastBlock) {
//#if DEBUG
//            Serial.println("Was the last block.");
//#endif
//            break;
//        }
    }

#if DEBUG
    Serial.print("availableMemory=");
    Serial.println(availableMemory());
    Serial.println("Sending the finished bytes...");
#endif

    if (!_radio->write(&finishedBytes, sizeof(finishedBytes))) {
#if DEBUG
        Serial.println("Not delivered.");
#endif
        return false;
    }

#if DEBUG
    Serial.println("Starting listening...");
#endif

    _radio->startListening();

#if DEBUG
    Serial.println("Success sending!");
#endif

    return true;
}

bool RadioManager::read(StaticJsonDocument<MSG_SIZE> &jsonBuffer) {
    char buffer[MSG_SIZE];
    char blockBuffer[BLOCK_SIZE];

    _radio->read(&blockBuffer, BLOCK_SIZE);

#if DEBUG
    Serial.print("Read block: ");
    Serial.println(blockBuffer);
#endif

    if (strcmp(blockBuffer, startedBytes) != 0) {
#if DEBUG
        Serial.println("It is not started bytes.");
#endif
        return false;
    }

    unsigned long startGettingAt = millis();

    unsigned short int part = 0;

    while (millis() - startGettingAt < 2000) {
        if (!_radio->available()) {
            delay(MSG_DELAY);
            continue;
        }

        _radio->read(&blockBuffer, BLOCK_SIZE);
#if DEBUG
        Serial.print("Read block: ");
        Serial.println(blockBuffer);
        Serial.print("availableMemory=");
        Serial.println(availableMemory());
#endif

        if (strcmp(blockBuffer, startedBytes) == 0) {
            Serial.println("Got started bytes.");
            buffer[0] = '\0';
            part = 0;
            startGettingAt = millis();
            continue;
        }

        if (strcmp(blockBuffer, finishedBytes) == 0) {
#if DEBUG
            Serial.println("Got finished bytes.");
#endif

#if ENCRYPT
#if DEBUG
            Serial.println("Start decryption...");
#endif
            for (unsigned int i = 0; i < MSG_SIZE; i += _aes128->blockSize()) {
                _aes128->clear();
                _aes128->setKey(aue128_key, _aes128->keySize());
                _aes128->decryptBlock(&buffer[i], &buffer[i]);
            }
#endif
            deserializeJson(jsonBuffer, buffer);
            return true;
        }

#if DEBUG
        Serial.println("Saving block...");
#endif

        strncpy(buffer + part, blockBuffer, BLOCK_SIZE);

#if DEBUG
        Serial.print("Part: ");
        Serial.println(part);
#endif

        part += BLOCK_SIZE;

#if DEBUG
        Serial.print("All buffer: ");
        Serial.println(buffer);
#endif

        startGettingAt = millis();
    }

    Serial.print("Time limit.");
    return false;
}


bool RadioManager::hasInputData() {
    return _radio->available();
}