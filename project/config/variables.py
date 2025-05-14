import datetime
import json
import os
import time
import typing
from os.path import dirname
from pathlib import Path

import pytz
from crontab import CronTab

from libs.casual_utils.version_manager import VersionDetails


ROOT_DIR = Path(dirname(__file__)) / '..' / '..'
PROJECT_DIR = ROOT_DIR / 'project'
APPS_DIR = PROJECT_DIR / 'apps'

with open(os.path.join(ROOT_DIR, os.environ['CONFIG_PATH'])) as config_file:
    json_config = json.load(config_file)

# Version
version_details = VersionDetails()
VERSION = version_details.version

# Env
PROJECT_ENV = json_config['project_env']
DEBUG = json_config['debug']

# Telegram
TELEGRAM_CHAT_ID = json_config['telegram_chat_id']
TELEGRAM_TOKEN = json_config['telegram_token']
TELEGRAM_USERNAME = json_config['telegram_username']
TELEHOOKS_QUEUE_NAME = json_config['telehooks_queue_name']
TELEHOOKS_HOST = json_config['telehooks_host']

# Services
OPENWEATHERMAP_URL = json_config['openweathermap_url']

# CV
VIDEO_SRC = json_config['video_src']
IMSHOW = json_config['imshow']
IMAGE_RESOLUTION = json_config['image_resolution']
FPS = json_config['fps']

# Arduino
ARDUINO_TTY = json_config['arduino_tty']

# Databases
DATABASE_URL = json_config['database_url']
DATABASE_DEBUG = DEBUG
_raw_storage_time = json_config['storage_time'].split(' ')
STORAGE_TIME = datetime.timedelta(**{_raw_storage_time[1]: int(_raw_storage_time[0])})

# Time
TZ = json_config['tz']
PY_TZ = pytz.timezone(TZ)
os.environ['TZ'] = TZ
time.tzset()

# Sentry
SENTRY_DSN = json_config['sentry_dsn']

# Dropbox
DROPBOX_TOKEN = json_config['dropbox_token']

# Router
ROUTER_TYPE = json_config['router_type']
assert ROUTER_TYPE == 'tplink'
ROUTER_PASSWORD = json_config['router_password']
ROUTER_URL = json_config['router_url']

# Zigbee
ZIGBEE_MQ_HOST = json_config['zigbee_mq_host']
ZIGBEE_MQ_PORT = json_config['zigbee_mq_port']
ZIGBEE_AVAILABILITY_ACTIVE_TIMEOUT_CHECK = datetime.timedelta(
    minutes=json_config['zigbee_availability_active_timeout_check'],
)
ZIGBEE_AVAILABILITY_PASSIVE_TIMEOUT_CHECK = datetime.timedelta(
    minutes=json_config['zigbee_availability_passive_timeout_check'],
)

# WiFi devices
WIFI_DEVICES = json_config['wifi_devices']

# Other
SLEEPING_TIME = tuple(datetime.time.fromisoformat(t) for t in json_config['sleeping_time'])
NORMAL_HUMIDITY_RANGE = json_config['normal_humidity_range']
NORMAL_TEMPERATURE_RANGE = json_config['normal_temperature_range']
ARTIFICIAL_SUNRISE_SCHEDULES = tuple(CronTab(schedule) for schedule in json_config['artificial_sunrise_schedules'])


class SmartDeviceNames:
    TEMP_HUM_SENSOR_NAME_PREFIX = 'temp_hum_sensor:'

    MAIN_SMART_LAMP = 'lamp:main_room'
    WATER_LEAK_SENSOR_BATH = 'water_leak_sensor:bath'
    WATER_LEAK_SENSOR_KITCHEN_TAP = 'water_leak_sensor:kitchen:tap'
    WATER_LEAK_SENSOR_KITCHEN_BOTTOM = 'water_leak_sensor:kitchen:bottom'
    WATER_LEAK_SENSOR_WC = 'water_leak_sensor:wc'
    TEMP_HUM_SENSOR_WORK_ROOM = f'{TEMP_HUM_SENSOR_NAME_PREFIX}work_room'
    TEMP_HUM_SENSOR_BEDROOM = f'{TEMP_HUM_SENSOR_NAME_PREFIX}bedroom'
    MOTION_SENSOR_HALLWAY = 'motion_sensor:hallway'
    DOOR_SENSOR_NARNIA = 'door_sensor:narnia'

    WATER_LEAK_SENSORS: typing.ClassVar[set[str]] = {
        WATER_LEAK_SENSOR_BATH,
        WATER_LEAK_SENSOR_KITCHEN_TAP,
        WATER_LEAK_SENSOR_KITCHEN_BOTTOM,
        WATER_LEAK_SENSOR_WC,
    }

    TEMP_HUM_SENSORS: typing.ClassVar[set[str]] = {
        TEMP_HUM_SENSOR_WORK_ROOM,
        TEMP_HUM_SENSOR_BEDROOM,
    }

    ALL: typing.ClassVar[set[str]] = {
        MAIN_SMART_LAMP,
        MOTION_SENSOR_HALLWAY,
        DOOR_SENSOR_NARNIA,
        *TEMP_HUM_SENSORS,
        *WATER_LEAK_SENSORS,
    }
