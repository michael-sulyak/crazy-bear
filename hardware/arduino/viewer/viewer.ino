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
    bool isWaitingData = true;
    unsigned short cycledVarForWaitingData = 0;
    unsigned long lastReceivedDateAt = 0;
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
}

void loop() {
    checkSerialInput();

    if (radioTransmitter.hasInputData()) {
        processInputData();
    }

    if (!globalState.isWaitingData && millis() - globalState.lastReceivedDateAt > 60 * 1000) {
        globalState.isWaitingData = true;
    }

    if (globalState.isWaitingData) {
        printMsgForWaitingData();
    }

    if (millis() - globalState.lastUpdatedBatteryLevelAt > 60 * 1000) {
        printBatteryLevel(LCD_WIDTH - 1, 0);
        globalState.lastUpdatedBatteryLevelAt = millis();
    }

    processMhSensor();

    delay(MSG_DELAY);
}


void initLcd() {
    lcd.init();
    lcd.backlight();
    lcd.setCursor(0, 0);
}

void printInCenter(String text) {
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

void printSensorsData() {
    lcd.setCursor(0, 0);
    lcd.print("[Current stats]");
    printBatteryLevel(LCD_WIDTH - 1, 0);

    String value;
    unsigned short n;

    lcd.setCursor(0, 2);
    value = "Temperature: ";
    n = value.length();
    lcd.print(value);
    value = jsonBuffer["p"]["t"].as<String>();
    n += value.length();
    lcd.print(value);
    lcd.print("\xDF");
    lcd.print("C");
    clearLcd(LCD_WIDTH - (n + 2));

    lcd.setCursor(0, 3);
    value = "Humidity: ";
    n = value.length();
    lcd.print(value);
    value = jsonBuffer["p"]["h"].as<String>();
    n += value.length();
    lcd.print(value);
    lcd.print("%");
    clearLcd(LCD_WIDTH - (n + 1));
}

float readVolt() {
    const int sensorValue = analogRead(A0);
    return sensorValue * (5.0 / 1024.00);
}


void printBatteryLevel(const unsigned short xPos, const unsigned short yPos) {
    double currentVolt = readVolt();

    if (currentVolt > 4.0) {
        const byte batteryLevel[8] = {
                B01110,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt <= 4.0 && currentVolt > 3.8) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt <= 3.8 && currentVolt > 3.6) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt <= 3.6 && currentVolt > 3.4) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt <= 3.4 && currentVolt > 3.2) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt <= 3.2 && currentVolt > 3.0) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    } else if (currentVolt < 3.0) {
        const byte batteryLevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
        };
        lcd.createChar(0, batteryLevel);
    }

    lcd.setCursor(xPos, yPos);
    lcd.write(byte(0));
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
                lcd.print("[Current stats]");
            }

            printSensorsData();
            globalState.lastReceivedDateAt = millis();
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
    if (millis() - globalState.lastLcdSwitchingAt > 3 * 1000) {
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

        delay(40);
    }

    delay(100);
}

void clearLcd(unsigned short n) {
    for (unsigned short i = 0; i < n; ++i) {
        lcd.print(" ");
    }
}
