#include <DHT_U.h>
#include <DHT.h>

#include <ArduinoJson.h>


const int PIR_SENSOR_PIN = A0;
const int DHT_SENSOR_PIN = 2;

const char typeSetSettings[] = "set_settings";
const char typeGetSettings[] = "get_settings";
const char typeSettings[] = "settings";
const char typeSensors[] = "sensors";

int ttl = 10 * 1000;

StaticJsonDocument<256> sensors;
StaticJsonDocument<256> inputData;
StaticJsonDocument<256> response;

DHT dhtSensor(DHT_SENSOR_PIN, DHT22);

void setup() {
  Serial.begin(9600);
  
  dhtSensor.begin();
}

void loop() {
  if (Serial.available() > 0) {
    deserializeJson(inputData, Serial);

    if (inputData["type"] == typeSetSettings) {
        ttl = inputData["payload"]["ttl"];
    } else if (inputData["type"] == typeGetSettings) {
        response["type"] = typeSettings;
        response["payload"]["ttl"] = ttl;
        send_data(response);
        response.clear();
    }

    inputData.clear();
  }

  sensors["type"] = typeSensors;
  sensors["payload"]["pir_sensor"] = analogRead(PIR_SENSOR_PIN);
  sensors["payload"]["humidity"] = dhtSensor.readHumidity();
  sensors["payload"]["temperature"] = dhtSensor.readTemperature();
  
  send_data(sensors);
  
  delay(ttl);
}

void send_data(StaticJsonDocument<256> data) {
  data["sent_at"] = millis();
  serializeJson(data, Serial);
  Serial.println();
}
