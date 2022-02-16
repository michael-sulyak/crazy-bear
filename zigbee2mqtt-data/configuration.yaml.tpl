# Let new devices join our zigbee network
permit_join: false

# Docker-Compose makes the MQTT-Server available using "mqtt" hostname
mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://zigbee_mq

# Zigbee Adapter path
serial:
  port: /dev/ttyACM0

# Enable the Zigbee2MQTT frontend
frontend:
  host: 0.0.0.0
  port: 8080
  auth_token: secret

# Let Zigbee2MQTT generate a new network key on first start
advanced:
  network_key: GENERATE
