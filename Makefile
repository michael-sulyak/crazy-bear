arduino_list:
	arduino-cli board list

arduino_build:
	echo "Compiling..." && \
	arduino-cli compile ./hardware/arduino/viewer --port /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328old --verify && \
	echo "Uploading..." && \
	arduino-cli upload ./hardware/arduino/viewer --port /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328old --verify && \
	echo "Done."

arduino_monitor:
	arduino-cli monitor --port /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328old
