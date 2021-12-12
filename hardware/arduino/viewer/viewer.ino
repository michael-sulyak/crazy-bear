#include <ArduinoJson.h>

// For radio
#include "radio_manager/radio_manager.cpp"
#include <RF24.h>  // https://nrf24.github.io/RF24/

// For LCD
#include <Wire.h>
#include <LiquidCrystal_I2C.h>


#define PIN_CE 7
#define PIN_CSN 8
#define RADIO_ADDRESS 0xF0F0F0F066

#define LCD_WIDTH 20
#define LCD_HEIGHT 3

#define typeSensors "sensors"


LiquidCrystal_I2C lcd(0x27, LCD_WIDTH, LCD_HEIGHT);

RF24 radio(PIN_CE, PIN_CSN);
RadioManager radioManager(radio);
StaticJsonDocument<MSG_SIZE> jsonBuffer;

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
    lcd.setCursor(1, 1);
    lcd.print("Temperature: ");
    lcd.print(jsonBuffer["p"]["t"].as<String>());
    lcd.print("C");
    lcd.setCursor(1, 2);
    lcd.print("Humidity: ");
    lcd.print(jsonBuffer["p"]["h"].as<String>());
    lcd.print("%");
}

void setup() {
    Serial.begin(9600);
    initLcd();
    radioManager.initRadio();
    printInCenter("Waiting data...");
}

void loop() {
    //  lcd.backlight();

    if (radioManager.hasInputData()) {
        Serial.println("Has something");

        if (radioManager.read(jsonBuffer)) {
            serializeJson(jsonBuffer, Serial);
            Serial.println();

            if (jsonBuffer["t"].as<String>() == typeSensors) {
                printSensorsData();
            }

            jsonBuffer.clear();
        }

        Serial.print("Available memory: ");
        Serial.print(availableMemory());
        Serial.println(" b.");
    }

    delay(200);
}
