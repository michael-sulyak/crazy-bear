#include "radio_transmitter.hh"

#include <ArduinoJson.h>

// For radio
#include <SPI.h>
#include <nRF24L01.h>  // https://nrf24.github.io/RF24/
#include <RF24.h>  // https://nrf24.github.io/RF24/


int availableMemory() {
    int size = 2048;  // For ATmega328
    byte *buf;
    while ((buf = (byte *) malloc(--size)) == NULL);
    free(buf);
    return size;
}

RadioTransmitter::RadioTransmitter(RF24 &radio) {
    _radio = &radio;
}

void RadioTransmitter::init() {
    _radio->begin();
    _radio->setChannel(RADIO_CHANNEL);
    _radio->setDataRate(RF24_250KBPS);
    _radio->setPALevel(RF24_PA_MIN);
    _radio->openWritingPipe((const uint8_t *) RADIO_ADDRESS);
    _radio->openReadingPipe(0, (const uint8_t *) RADIO_ADDRESS);
    _radio->setAutoAck(true);
    _radio->startListening();
}

bool RadioTransmitter::send(StaticJsonDocument<MSG_SIZE> &jsonBuffer) {
    _radio->stopListening();

    if (isDebugMode) {
        Serial.println("Start sending...");
    }

    if (!_radio->write(&startedBytes, sizeof(startedBytes))) {
        if (isDebugMode) {
            Serial.println("Not delivered.");
        }

        return false;
    }

    delay(MSG_DELAY);

    if (isDebugMode) {
        Serial.println("Serializing JSON...");
    }

    char buffer[MSG_SIZE];
    serializeJson(jsonBuffer, buffer);

    if (isDebugMode) {
        Serial.print("Buffer for sending: ");
        Serial.println(buffer);
    }

    for (unsigned int i = 0; i < MSG_SIZE; i += BLOCK_SIZE) {
        bool isLastBlock = false;

        for (unsigned int j = i; j < i + BLOCK_SIZE; ++j) {
            if (buffer[j] == '\0') {
                isLastBlock = true;
                break;
            }
        }

        if (isDebugMode) {
            Serial.print("Block for process:");
            Serial.println(i / BLOCK_SIZE + 1);
        }

        if (!_radio->write(&buffer[i], BLOCK_SIZE)) {
            if (isDebugMode) {
                Serial.println("Not delivered.");
            }

            return false;
        }

        delay(MSG_DELAY);

        if (isLastBlock) {
            if (isDebugMode) {
                Serial.println("It was the last block.");
            }

            break;
        }
    }

    if (isDebugMode) {
        Serial.print("availableMemory=");
        Serial.println(availableMemory());
        Serial.println("Sending the finished bytes...");
    }

    if (!_radio->write(&finishedBytes, sizeof(finishedBytes))) {
        if (isDebugMode) {
            Serial.println("Not delivered.");
        }

        return false;
    }

    if (isDebugMode) {
        Serial.println("Starting listening...");
    }

    _radio->startListening();

    if (isDebugMode) {
        Serial.println("Success sending!");
    }

    return true;
}

bool RadioTransmitter::read(StaticJsonDocument<MSG_SIZE> &jsonBuffer) {
    char buffer[MSG_SIZE];
    char blockBuffer[BLOCK_SIZE];

    _radio->read(&blockBuffer, BLOCK_SIZE);

    if (isDebugMode) {
        Serial.print("Read block: ");
        Serial.println(blockBuffer);
    }

    // Don't start process messages without the started bytes.
    if (strcmp(blockBuffer, startedBytes) != 0) {
        if (isDebugMode) {
            Serial.print("\"");
            Serial.print(blockBuffer);
            Serial.println("\" - it is not started bytes.");
        }

        return false;
    }

    unsigned long startGettingAt = millis();

    unsigned short int part = 0;

    // Read blocks until the ended bytes.
    while (millis() - startGettingAt < 2000) {
        if (!_radio->available()) {
            delay(MSG_DELAY);
            continue;
        }

        _radio->read(&blockBuffer, BLOCK_SIZE);

        if (isDebugMode) {
            Serial.print("Read block: ");
            Serial.println(blockBuffer);
            Serial.print("Available memory: ");
            Serial.println(availableMemory());
            Serial.print(" b.");
        }

        if (strcmp(blockBuffer, startedBytes) == 0) {
            Serial.println("Got started bytes.");
            buffer[0] = '\0';
            part = 0;
            startGettingAt = millis();
            continue;
        }

        if (strcmp(blockBuffer, finishedBytes) == 0) {
            if (isDebugMode) {
                Serial.println("Got finished bytes.");
            }

            deserializeJson(jsonBuffer, buffer);
            return true;
        }


        if (isDebugMode) {
            Serial.println("Saving block...");
        }

        strncpy(buffer + part, blockBuffer, BLOCK_SIZE);


        if (isDebugMode) {
            Serial.print("Part: ");
            Serial.println(part);
        }

        part += BLOCK_SIZE;


        if (isDebugMode) {
            Serial.print("All buffer: ");
            Serial.println(buffer);
        }

        startGettingAt = millis();
    }

    if (isDebugMode) {
        Serial.print("Time limit.");
    }

    return false;
}


bool RadioTransmitter::hasInputData() {
    return _radio->available();
}

void RadioTransmitter::powerUp() {
    _radio->powerUp();
    delay(5);
}

void RadioTransmitter::powerDown() {
    _radio->powerDown();
    delay(5);
}

bool RadioTransmitter::ping() {
    const char text[] = "ping";
    return _radio->write(&text, sizeof(text));
}

