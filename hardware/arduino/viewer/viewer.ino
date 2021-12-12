#include <ArduinoJson.h>

// For radio
#include "radio_transmitter/radio_transmitter.cpp"

// For LCD
#include <Wire.h>
#include <LiquidCrystal_I2C.h>


#define PIN_CE 7
#define PIN_CSN 8
#define RADIO_ADDRESS 0xF0F0F0F066

#define LCD_WIDTH 20
#define LCD_HEIGHT 3

#define typeSensors "sensors"
#define typeSilentMode "sm"
#define ON "on"
#define OFF "off"


LiquidCrystal_I2C lcd(0x27, LCD_WIDTH, LCD_HEIGHT);

RF24 radio(PIN_CE, PIN_CSN);
RadioTransmitter radioTransmitter(radio);
StaticJsonDocument<MSG_SIZE> jsonBuffer;

bool isWaitingData = true;

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

void printSensorsData() {
    lcd.clear();
    lcd.setCursor(0, 1);
    lcd.print("Sensors");
    lcd.setCursor(0, 2);
    lcd.print("Temperature: ");
    lcd.print(jsonBuffer["p"]["t"].as<String>());
    lcd.print("\xDF");
    lcd.print("C");
    lcd.setCursor(0, 3);
    lcd.print("Humidity: ");
    lcd.print(jsonBuffer["p"]["h"].as<String>());
    lcd.print("%");
}

float readVolt() {
    const int sensorValue = analogRead(A0);  // Read the A0 pin value
    return sensorValue * (5.00 / 1023.00) * 2;  // Convert the value to a true voltage.
}

void printBatteryLevel(const int xPos, const int yPos) {
    double currentVolt = readVolt();

    // Check if voltage is bigger than 4.2 volt so this is a power source
    if (currentVolt > 4.2) {
        byte batlevel[8] = {
                B01110,
                B11111,
                B10101,
                B10001,
                B11011,
                B11011,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 4.2 && currentVolt > 4.0) {
        byte batlevel[8] = {
                B01110,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 4.0 && currentVolt > 3.8) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 3.8 && currentVolt > 3.6) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 3.6 && currentVolt > 3.4) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 3.4 && currentVolt > 3.2) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt <= 3.2 && currentVolt > 3.0) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    } else if (currentVolt < 3.0) {
        byte batlevel[8] = {
                B01110,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B10001,
                B11111,
        };

        lcd.createChar(0, batlevel);
        lcd.setCursor(xPos, yPos);
        lcd.write(byte(0));
    }
}

void setup() {
    Serial.begin(9600);
    initLcd();
    radioTransmitter.init();
    printInCenter("Waiting data...");
}

void loop() {
    if (radioTransmitter.hasInputData()) {
        Serial.println("Has something");

        if (radioTransmitter.read(jsonBuffer)) {
            serializeJson(jsonBuffer, Serial);
            Serial.println();

            if (jsonBuffer["t"].as<String>() == typeSensors) {
                isWaitingData = false;
                printSensorsData();
            } else if (jsonBuffer["t"].as<String>() == typeSilentMode) {
                if (jsonBuffer["v"].as<String>() == ON) {
                    lcd.noBacklight();
                    lcd.clear();
                    radioTransmitter.powerDown();
                    delay(jsonBuffer["s"].as<int>() * 60 * 1000);
                } else if (jsonBuffer["v"].as<String>() == OFF) {
                    isWaitingData = true;
                    printInCenter("Waiting data...");
                    lcd.backlight();
                    radioTransmitter.powerUp();
                }
            }

            jsonBuffer.clear();
        }

        Serial.print("Available memory: ");
        Serial.print(availableMemory());
        Serial.println("b");
    }

    if (!isWaitingData) {
        lcd.setCursor(0, 0);
        lcd.print("[Viewer]");
    }

    printBatteryLevel(LCD_WIDTH - 1, 0);

    delay(MSG_DELAY);
}
