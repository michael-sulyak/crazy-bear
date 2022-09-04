#include <ArduinoJson.h>

// For radio"
#include "radio_transmitter/radio_transmitter.cpp"

// For LCD"
#include <Wire.h>
#include <LiquidCrystal_I2C.h>


// Pins for radio:
#define PIN_CE 10
#define PIN_CSN 9

// Pins for LCD:
#define LCD_WIDTH 20
#define LCD_HEIGHT 4

// Other pins:
#define PIN_MH 2

// Vars:
#define TYPE_SENSORS "sensors"
#define TYPE_SILENT_MODE "sm"
#define ON "on"
#define OFF "off"
#define MSG_FOR_WAITING_DATA "Waiting data   "

// Global objects:
LiquidCrystal_I2C lcd(0x27, LCD_WIDTH, LCD_HEIGHT);
RF24 radio(PIN_CE, PIN_CSN);
RadioTransmitter radioTransmitter(radio);
StaticJsonDocument<MSG_SIZE> jsonBuffer;

// Global state:
struct {
    const unsigned short radioSleep = 20 * 1000 - 5 * 1000;  // radioDelay - 5 sec.
    const unsigned short resetAfter = 3 * 60 * 1000;
    bool isWaitingData = true;
    unsigned short cycledVarForWaitingData = 0;
    unsigned long lastReceivedDataAt = 0;
    unsigned long lastUpdatedBatteryLevelAt = 0;
    unsigned long lastLcdSwitchingAt = 0;
    bool lsdIsOn = true;
    bool isDebugMode = false;
} globalState;


void setup() {
    Serial.begin(9600);
    initLcd();
    radioTransmitter.init();
    radioTransmitter.powerUp();
    pinMode(PIN_MH, INPUT);
    showLaunchScreen();
    printInCenter(MSG_FOR_WAITING_DATA);
    printHeadIcons();
}

void loop() {
    checkSerialInput();

    if (radioTransmitter.hasInputData()) {
        processInputData();
    }

    const long diffReceivedDataTime = millis() - globalState.lastReceivedDataAt;
    if (globalState.lastReceivedDataAt > 0 && diffReceivedDataTime < globalState.radioSleep && !globalState.isWaitingData) {
        if (radioTransmitter.isOn) {
            radioTransmitter.powerDown();
        }
    } else if (!radioTransmitter.isOn) {
        radioTransmitter.powerUp();
    }

    if (!globalState.isWaitingData && millis() - globalState.lastReceivedDataAt > globalState.resetAfter) {
        globalState.isWaitingData = true;
        lcd.clear();
        printInCenter(MSG_FOR_WAITING_DATA);
        printHeadIcons();
    }

    if (globalState.isWaitingData) {
        printMsgForWaitingData();
    }

//     if (millis() - globalState.lastUpdatedBatteryLevelAt > 60 * 1000) {
//         printBatteryLevel(LCD_WIDTH - 1, 0);
//         globalState.lastUpdatedBatteryLevelAt = millis();
//     }

    printHeadIcons();

    processMhSensor();

    delay(MSG_DELAY);
}


void initLcd() {
    lcd.init();
    lcd.backlight();
    lcd.setCursor(0, 0);
}

void printInCenter(const String text) {
    lcd.clear();
    lcd.setCursor((LCD_WIDTH - text.length()) / 2, LCD_HEIGHT / 2);
    lcd.print(text);
}

void checkSerialInput() {
    if (Serial.available() == 0) {
        return;
    }

    String input = Serial.readString();
    input.trim();

    if (input == "debug=on") {
        globalState.isDebugMode = true;
        radioTransmitter.isDebugMode = true;
        Serial.println("Debug enabled.");
    } else if (input == "debug=off") {
        globalState.isDebugMode = false;
        radioTransmitter.isDebugMode = false;
        Serial.println("Debug disabled.");
    } else {
        Serial.println("Unknown command.");
    }
}

void printTitle() {
    printChar(9, 0, 0);
    lcd.print(" Stats");
}

void printSensorsData() {
    printTitle();

    String value;
    unsigned short n;

    printChar(7, 0, 2);
    lcd.print(" ");
    n = 2;
    if (jsonBuffer["p"]["t"].isNull()) {
        value = "?";
    } else {
        value = jsonBuffer["p"]["t"].as<String>();
    }
    n += value.length();
    lcd.print(value);
    lcd.print("\xDF");
    lcd.print("C");
    clearLcd(4 - value.length());

    printChar(8, 0, 3);
    lcd.print(" ");
    n = 2;
    if (jsonBuffer["p"]["h"].isNull()) {
        value = "?";
    } else {
        value = jsonBuffer["p"]["h"].as<String>();
    }
    n += value.length();
    lcd.print(value);
    lcd.print("%");
    clearLcd(4 - value.length());

    printChar(10, 11, 2);
    lcd.print(" ");
    n = 2;
    if (jsonBuffer["p"]["a"].isNull()) {
        value = "?";
    } else {
        value = jsonBuffer["p"]["a"].as<String>();
    }
    n += value.length();
    lcd.print(value);
    lcd.print("%");
    clearLcd(4 - value.length());
}

float readVolt() {
    const int sensorValue = analogRead(A0);
    return sensorValue * (5.0 / 1024.0);
}

unsigned short int createChar(const unsigned short n) {
    /* Note: Need to update all chars after updating one to fix issues. */

    if (n == 0) {
        const byte batteryLevel[8] = {
            B01110,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 1) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 2) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B10001,
            B11111,
            B11111,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 3) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B10001,
            B10001,
            B11111,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 4) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B10001,
            B10001,
            B10001,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 5) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B10001,
            B10001,
            B10001,
            B10001,
            B11111,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 6) {
        const byte batteryLevel[8] = {
            B01110,
            B10001,
            B10001,
            B10001,
            B10001,
            B10001,
            B10001,
            B11111
        };
        lcd.createChar(0, batteryLevel);
        return 0;
    } else if (n == 7) {
        const byte temperature[] = {
            B00000,
            B01011,
            B01011,
            B11100,
            B01000,
            B01000,
            B01000,
            B00110
        };
        lcd.createChar(1, temperature);
        return 1;
    } else if (n == 8) {
        const byte humidity[] = {
            B00000,
            B00100,
            B00100,
            B01110,
            B11001,
            B11101,
            B11111,
            B01110
        };
        lcd.createChar(2, humidity);
        return 2;
    } else if (n == 9) {
        const byte logo[] = {
            B00000,
            B00010,
            B10010,
            B10010,
            B11110,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(3, logo);
        return 3;
    } else if (n == 10) {
        const byte air[] = {
            B01100,
            B00100,
            B11000,
            B00000,
            B11110,
            B00001,
            B11001,
            B01010
        };
        lcd.createChar(4, air);
        return 4;
    } else if (n == 11) {
        const byte signalLevel[] = {
            B00011,
            B00011,
            B00011,
            B01111,
            B01111,
            B11111,
            B11111,
            B11111
        };
        lcd.createChar(5, signalLevel);
        return 5;
    } else if (n == 12) {
        const byte signalLevel[] = {
            B00000,
            B00000,
            B00000,
            B00110,
            B00110,
            B11110,
            B11110,
            B11110
        };
        lcd.createChar(5, signalLevel);
        return 5;
    } else if (n == 13) {
        const byte signalLevel[] = {
            B00000,
            B00000,
            B00000,
            B00000,
            B00000,
            B11000,
            B11000,
            B11000
        };
        lcd.createChar(5, signalLevel);
        return 5;
    } else if (n == 14) {
        const byte radioIsOn[] = {
            B00010,
            B01001,
            B00101,
            B10101,
            B10101,
            B00101,
            B01001,
            B00010
        };
        lcd.createChar(6, radioIsOn);
        return 6;
    } else if (n == 15) {
        const byte radioIsOff[] = {
            B00000,
            B00000,
            B00100,
            B01110,
            B01110,
            B00100,
            B00000,
            B00000
        };
        lcd.createChar(6, radioIsOff);
        return 6;
    }
}

void printHeadIcons() {
    if (radioTransmitter.isOn) {
        printChar(14, LCD_WIDTH - 3, 0);
    } else {
        printChar(15, LCD_WIDTH - 3, 0);
    }

    printSignalLevel(LCD_WIDTH - 2, 0);
    printBatteryLevel(LCD_WIDTH - 1, 0);
}

void printBatteryLevel(const unsigned short xPos, const unsigned short yPos) {
    const float currentVolt = readVolt();

    if (currentVolt >= 4.6) {
        printChar(0, xPos, yPos);
    } else if (currentVolt <= 4.6 && currentVolt > 4.2) {
        printChar(1, xPos, yPos);
    } else if (currentVolt <= 4.2 && currentVolt > 3.8) {
        printChar(2, xPos, yPos);
    } else if (currentVolt <= 3.8 && currentVolt > 3.6) {
        printChar(3, xPos, yPos);
    } else if (currentVolt <= 3.6 && currentVolt > 3.4) {
        printChar(4, xPos, yPos);
    } else if (currentVolt <= 3.4 && currentVolt > 3.2) {
        printChar(5, xPos, yPos);
    } else if (currentVolt <= 3.2) {
        printChar(6, xPos, yPos);
    }
}

void printSignalLevel(const unsigned short xPos, const unsigned short yPos) {
    const long diff = millis() - globalState.lastReceivedDataAt;

    if (diff < globalState.radioSleep * 1.5) {
        printChar(11, xPos, yPos);
    } else if (diff < globalState.radioSleep * 2) {
        printChar(12, xPos, yPos);
    } else if (diff < globalState.radioSleep * 3) {
        printChar(13, xPos, yPos);
    } else {
        lcd.setCursor(xPos, yPos);
        lcd.print(" ");
    }
}

void printChar(const unsigned short n, const unsigned short xPos, const unsigned short yPos) {
    const unsigned short result = createChar(n);
    lcd.setCursor(xPos, yPos);  // It needs to be after `createChar`
    lcd.write(result);
}

void printMsgForWaitingData() {
    const short c = 400 / MSG_DELAY;

    for (unsigned short i = 0; i < 3; ++i) {
        lcd.setCursor(14 + i, 2);
        if (((i + 1) * c) < globalState.cycledVarForWaitingData) {
            lcd.print(".");
        } else {
            lcd.print(" ");
        }
    }

    ++globalState.cycledVarForWaitingData;

    if (globalState.cycledVarForWaitingData >= 4 * c) {
        globalState.cycledVarForWaitingData = 0;
    }
}

void processInputData() {
    if (globalState.isDebugMode) {
        Serial.println("Has something");
    }

    if (radioTransmitter.read(jsonBuffer)) {
        if (globalState.isDebugMode) {
            serializeJson(jsonBuffer, Serial);
            Serial.println();
        }

        if (jsonBuffer["t"].as<String>() == TYPE_SENSORS) {
            if (globalState.isWaitingData) {
                globalState.isWaitingData = false;
                lcd.clear();
                printTitle();
                printHeadIcons();
            }

            printSensorsData();
            globalState.lastReceivedDataAt = millis();
        } else if (jsonBuffer["t"].as<String>() == TYPE_SILENT_MODE) {
            if (jsonBuffer["v"].as<String>() == ON) {
                lcd.noBacklight();
                lcd.clear();
                radioTransmitter.powerDown();
                delay(jsonBuffer["s"].as<int>() * 60 * 1000);
            } else if (jsonBuffer["v"].as<String>() == OFF) {
                globalState.isWaitingData = true;
                printInCenter(MSG_FOR_WAITING_DATA);
                lcd.backlight();
                radioTransmitter.powerUp();
            }
        }

        jsonBuffer.clear();
    }


    if (globalState.isDebugMode) {
       Serial.print("Available memory: ");
       Serial.print(availableMemory());
       Serial.print(" b.");
    }
}

void processMhSensor() {
    if (millis() - globalState.lastLcdSwitchingAt < 3 * 1000) {
        return;
    }

    if (digitalRead(PIN_MH) == HIGH) {
        if (globalState.lsdIsOn) {
            globalState.lsdIsOn = false;
            lcd.noBacklight();
            globalState.lastLcdSwitchingAt = millis();
        }
    } else {
        if (!globalState.lsdIsOn) {
            globalState.lsdIsOn = true;
            lcd.backlight();
            globalState.lastLcdSwitchingAt = millis();
        }
    }
}


void showLaunchScreen() {
    for (unsigned short i = 0; i < LCD_WIDTH; ++i) {
        for (unsigned short j = 0; j < LCD_HEIGHT; ++j) {
            lcd.setCursor(i, j);
            lcd.print(">");
        }

        delay(30);
    }

    delay(100);
}

void clearLcd(unsigned short n) {
    for (unsigned short i = 0; i < n; ++i) {
        lcd.print(" ");
    }
}
