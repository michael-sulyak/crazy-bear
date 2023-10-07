echo "Updating dependencies..."
sudo apt update && sudo apt upgrade

sudo apt install -y \
    fail2ban \
    python3-pip \
    docker.io \
    unzip \
    raspi-config \
    wiringpi \
    python3-rpi.gpio \
    python3-rpi.gpio \
    ipython3 \
    cmake

sudo pip3 install \
    RPi.GPIO


echo "Enabling UFW..."
sudo ufw allow 22 && \
  sudo ufw allow 8443/udp && \
  sudo ufw allow 8080 && \
  sudo ufw enable


echo "Configuring docker..."
sudo groupadd docker && \
  sudo usermod -aG docker $USER && \
  newgrp docker && \
  sudo systemctl enable docker

echo "Installing dependencies for Arduino..."
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh && \
  arduino-cli core update-index && \
  arduino-cli core install arduino:avr && \
  arduino-cli lib install RF24 "DHT sensor library" Crypto ArduinoJson "LiquidCrystal I2C" MemoryUsage

echo "Building app..."
docker-compose -p crazy_bear -f docker-compose.prod.yml build

echo "Starting app..."
docker-compose -p crazy_bear -f docker-compose.prod.yml up -d

