#include "config.hh"

#include <ArduinoJson.h>

// For radio
#include <RF24.h>  // https://nrf24.github.io/RF24/


int availableMemory();

class RadioTransmitter {
public:
    bool isDebugMode = false;
    bool isOn = false;
    RadioTransmitter(RF24 &radio);
    void init();
    bool send(StaticJsonDocument<MSG_SIZE> &jsonBuffer);
    bool read(StaticJsonDocument<MSG_SIZE> &jsonBuffer);
    bool hasInputData();
    void powerUp();
    void powerDown();
    bool ping();

private:
    RF24 *_radio;
    const char startedBytes[14] = "#~~~START~~~#";
    const char finishedBytes[12] = "#~~~END~~~#";
};
