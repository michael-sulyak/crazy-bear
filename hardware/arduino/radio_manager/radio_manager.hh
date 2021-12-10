#include <ArduinoJson.h>

// For radio
#include <RF24.h>  // https://nrf24.github.io/RF24/

// For crypto
#include <AES.h>  // https://rweather.github.io/arduinolibs/crypto.html


#define BLOCK_SIZE 32
#define MSG_SIZE 64


int availableMemory();

void rawRadioRead(RF24 &radio);

class RadioManager {
public:
    RadioManager(RF24 &radio);

    void initRadio();

    bool send(StaticJsonDocument<MSG_SIZE> &jsonBuffer);

    bool read(StaticJsonDocument<MSG_SIZE> &jsonBuffer);

    bool hasInputData();

private:
    RF24 *_radio;
    AES128 *_aes128;
    const char startedBytes[14] = "#~~~START~~~#";
    const char finishedBytes[12] = "#~~~END~~~#";
};
