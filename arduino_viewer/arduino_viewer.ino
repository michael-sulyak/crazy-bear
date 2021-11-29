#include <ArduinoJson.h>

// For LCD
#include <Wire.h> 
#include <LiquidCrystal_I2C.h>

// For radio
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h> 

#define PIN_CE 7
#define PIN_CSN 8
#define RADIO_ADDRESS 0xF0F0F0F066

#define LCD_WIDTH 20
#define LCD_HEIGHT 3


class RF24Adapter {
 public:
  RF24Adapter(RF24 &radio) : _radio(&radio) {}

  int read() {
    char buf[1];
    _radio->read(buf, 1);
    return buf[0];
  }

  size_t readBytes(char *buffer, size_t length) {
    _radio->read(buffer, static_cast<uint8_t>(length));
    return length;
  }

  size_t write(uint8_t c) {
    return _radio->write(&c, 1) ? 1 : 0;
  }

  size_t write(const uint8_t *buffer, size_t length) {
    return _radio->write(buffer, static_cast<uint8_t>(length)) ? length : 0;
  }

 private:
  RF24 *_radio;
};

LiquidCrystal_I2C lcd(0x27, LCD_WIDTH, LCD_HEIGHT);

RF24 radio(PIN_CE, PIN_CSN); 
RF24Adapter radioForArduinoJson(radio);
StaticJsonDocument<512> radioData;

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

void setup()
{
  initLcd();
  initRadio();
  delay(1000);
}

void loop()
{
  lcd.backlight();
  printInCenter("Sending data...");
//  radio.write(&potValue, 1);

  radioData["1"] = 42;
  serializeJson(radioData, radioForArduinoJson);
  
  delay(2000);
  printInCenter("Done");
  delay(2000);
  lcd.noBacklight();
  lcd.clear();
  delay(10000);
}


void initRadio() {
  radio.begin();
  radio.setChannel(115);
  radio.setDataRate (RF24_250KBPS);
  radio.setPALevel(RF24_PA_MIN);
  radio.openWritingPipe(RADIO_ADDRESS);
}
