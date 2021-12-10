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


LiquidCrystal_I2C lcd(0x27, LCD_WIDTH, LCD_HEIGHT);

RF24 radio(PIN_CE, PIN_CSN);
RadioManager radioManager(radio);
StaticJsonDocument<64> jsonBuffer;

void initLcd() {
    lcd.init();
    lcd.backlight();
    lcd.setCursor(0, 0);
    printInCenter("Initialization ...");
}

void printInCenter(String text) {
    lcd.clear();
    lcd.setCursor((LCD_WIDTH - text.length()) / 2, LCD_HEIGHT / 2);
    lcd.print(text);
}

void setup() {
    Serial.begin(9600);
    initLcd();
//   initRadio();
    radioManager.initRadio();
    delay(1000);
    Serial.println("Staring...");
}

void loop() {
    //  lcd.backlight();
    printInCenter("Sending data...");
    delay(2000);

    //  lcd.noBacklight();
    jsonBuffer["1"] = "a";
    jsonBuffer["2"] = "b";
    jsonBuffer["3"] = "c";
    jsonBuffer["4"] = "d";
    radioManager.send(jsonBuffer);
//  char buffer[64];
//  serializeJson(jsonBuffer, buffer);
//  radio.write(&buffer, sizeof(buffer));

    printInCenter("Done");
    delay(5000);
}


//void initRadio() {
//    radio.begin();
//    radio.setChannel(115);
//    radio.setDataRate(RF24_250KBPS);
//    radio.setPALevel(RF24_PA_MIN);
//    radio.openWritingPipe(RADIO_ADDRESS);
//}
