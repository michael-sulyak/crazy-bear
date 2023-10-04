#include <ArduinoJson.h>

#include <MemoryUsage.h>
STACK_DECLARE;

// For radio"
#include "JsonRadioTransmitter/JsonRadioTransmitter.cpp"

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
const unsigned int msgSize = 32 * 2;
RadioTransmitter<StaticJsonDocument<msgSize>> radioTransmitter(radio, "viewer", "root", 88);

// Global state:
struct {
    const unsigned long radioDelay = 60000;
    const unsigned long radioSleep = radioDelay - 5000;
    const unsigned long resetAfter = 1200000;
    const unsigned long lcdSwitch = 10000;
    bool isWaitingData = true;
    unsigned short cycledVarForWaitingData = 0;
    unsigned long lastReceivedDataAt = 0;
    unsigned long lastUpdatedBatteryLevelAt = 0;
    unsigned long lastLcdSwitchingAt = 0;
    bool lsdIsOn = true;
    bool debugMode = true;
} globalState;


void setup() {
    Serial.begin(9600);

    if (globalState.debugMode) {
        Serial.println("Start.");
        radioTransmitter.debugMode = true;
    }

    initLcd();
    radioTransmitter.msgSize = msgSize;
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

    const unsigned long now = millis();
    const unsigned long diffReceivedDataTime = now - globalState.lastReceivedDataAt;
    const bool needToTurnOnRadio = globalState.lastReceivedDataAt == 0 || diffReceivedDataTime > globalState.radioSleep || globalState.isWaitingData;
    const bool needToWaitNewData = now - globalState.lastReceivedDataAt > globalState.resetAfter;

//     Serial.print("now: ");
//     Serial.println(now);
//
//     Serial.print("diffReceivedDataTime: ");
//     Serial.println(diffReceivedDataTime);
//
//     Serial.print("needToTurnOnRadio: ");
//     Serial.println(needToTurnOnRadio);
//
//     Serial.print("needToWaitNewData: ");
//     Serial.println(needToWaitNewData);
//
//     Serial.print("radioSleep: ");
//     Serial.println(globalState.radioSleep);
//
//     Serial.print("radioDelay: ");
//     Serial.println(globalState.radioDelay);

    if (needToTurnOnRadio) {
        if (!radioTransmitter.isOn) {
            radioTransmitter.powerUp();
        }
    } else {
        if (radioTransmitter.isOn) {
            radioTransmitter.powerDown();
        }
    }

    if (!globalState.isWaitingData && needToWaitNewData) {
        globalState.isWaitingData = true;
        lcd.clear();
        printInCenter(MSG_FOR_WAITING_DATA);
        printHeadIcons();
    }

    if (globalState.isWaitingData) {
        printMsgForWaitingData();
    }

    printHeadIcons();

    processMhSensor();

    delay(100);
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
    if (!Serial.available()) {
        return;
    }

    String input = Serial.readString();
    input.trim();

    if (input == "debug=on") {
        globalState.debugMode = true;
        radioTransmitter.debugMode = true;
        Serial.println("Debug enabled.");
    } else if (input == "debug=off") {
        globalState.debugMode = false;
        radioTransmitter.debugMode = false;
        Serial.println("Debug disabled.");
    } else {
        Serial.println("Unknown command.");
    }
}

void printTitle() {
    printChar(9, 0, 0);
    lcd.print(" Stats");
}

void printSensorsData(StaticJsonDocument<msgSize> &jsonBuffer) {
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
    if (jsonBuffer["p"]["p"].isNull()) {
        value = "?";
    } else {
        value = jsonBuffer["p"]["p"].as<String>();
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

    if (currentVolt <= 3.4) {
        printChar(6, xPos, yPos);
    } else if (currentVolt <= 3.6) {
        printChar(5, xPos, yPos);
    }  else if (currentVolt <= 3.8 ) {
        printChar(4, xPos, yPos);
    } else if (currentVolt <= 4.0) {
        printChar(3, xPos, yPos);
    } else if (currentVolt <= 4.2) {
        printChar(2, xPos, yPos);
    } else if (currentVolt <= 4.4) {
        printChar(1, xPos, yPos);
    } else {
        printChar(0, xPos, yPos);
    }
}

void printSignalLevel(const unsigned short xPos, const unsigned short yPos) {
    const long diff = millis() - globalState.lastReceivedDataAt;

    if (globalState.lastReceivedDataAt == 0) {
        lcd.setCursor(xPos, yPos);
        lcd.print(" ");
    } else if (diff < globalState.radioDelay) {
        printChar(11, xPos, yPos);
    } else if (diff < globalState.radioDelay * 1.5) {
        printChar(12, xPos, yPos);
    } else if (diff < globalState.radioDelay * 2) {
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
    const short c = 4;

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
    if (globalState.debugMode) {
        Serial.println("Has something.");
    }

    StaticJsonDocument<msgSize> jsonBuffer;

    if (radioTransmitter.read(jsonBuffer)) {
        if (globalState.debugMode) {
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

            printSensorsData(jsonBuffer);
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
        } else {
            if (globalState.debugMode) {
               Serial.println("Unsupported type.");
            }
        }
    }

    if (globalState.debugMode) {
        MEMORY_PRINT_HEAPSIZE;
        MEMORY_PRINT_STACKSIZE;
        MEMORY_PRINT_FREERAM;
        MEMORY_PRINT_TOTALSIZE;
    }
}

void processMhSensor() {
    if (millis() - globalState.lastLcdSwitchingAt < globalState.lcdSwitch) {
        return;
    }

    if (digitalRead(PIN_MH) == HIGH) {
        if (globalState.lsdIsOn) {
            globalState.lsdIsOn = false;
            lcd.noBacklight();
//             globalState.lastLcdSwitchingAt = millis();
        }
    } else {
        if (!globalState.lsdIsOn) {
            globalState.lsdIsOn = true;
            lcd.backlight();
        }

        globalState.lastLcdSwitchingAt = millis();
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
