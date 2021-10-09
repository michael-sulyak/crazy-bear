#include <Wire.h> 
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 20, 3); // Указываем I2C адрес (наиболее распространенное значение), а также параметры экрана (в случае LCD 1602 - 2 строки по 16 символов в каждой 


void setup()
{
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0,0); 
  lcd.print("Hello");
  lcd.setCursor(0, 1);
  lcd.print("ArduinoMaster");
  lcd.setCursor(0, 2);
  lcd.print("12345678901234567890");
}

void loop()
{
}
