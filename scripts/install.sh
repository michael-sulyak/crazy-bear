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

#old
#===========
#
#echo "Installing dependencies..."
#sudo apt install -y \
#    fail2ban \
#    python3-pip \
#    python3-pigpio \
#    python3-matplotlib \
#    python3-pip \
#    docker.io \
#    docker-compose \
#    unzip && \
#    spi-tools && \
#    raspi-config (https://archive.raspberrypi.org/debian/pool/main/r/raspi-config/) && \
#    sudo pip3 install \
#    RPi.GPIO
#https://github.com/gpiozero/gpiozero/issues/837#issuecomment-706549501



echo "Enabling UFW..."
sudo ufw allow 22 && \
  sudo ufw allow 8443/udp && \
  sudo ufw allow 8080 && \
  sudo ufw enable

#echo "InstallING OpenCV..."
#sudo apt install python3-opencv

echo "Configuring docker..."
sudo groupadd docker && \
  sudo usermod -aG docker $USER && \
  newgrp docker && \
  sudo systemctl enable docker

#echo "Installing other dependencies..."
#sudo apt install -y \
#    libfreetype6-dev \
#    pkg-config \
#    libblas3 \
#    liblapack3 \
#    liblapack-dev \
#    libblas-dev \
#    libavcodec-dev \
#    libavformat-dev \
#    libswscale-dev \
#    libv4l-dev \
#    libgdk-pixbuf2.0-dev \
#    libpango1.0-dev \
#    libgtk2.0-dev \
#    libgtk-3-dev \
#    libfontconfig1-dev \
#    libcairo2-dev \
#    libatlas-base-dev \
#    gfortran \
#    libhdf5-dev \
#    libhdf5-103 \
#    python3-pyqt5

echo "Installing dependencies for Arduino..."
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh && \
  arduino-cli core update-index && \
  arduino-cli core install arduino:avr && \
  arduino-cli lib install RF24 "DHT sensor library" Crypto ArduinoJson "LiquidCrystal I2C" MemoryUsage

echo "Building app..."
docker-compose -p crazy_bear -f docker-compose.prod.yml build

echo "Starting app..."
docker-compose -p crazy_bear -f docker-compose.prod.yml up -d
