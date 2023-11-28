import datetime
import time
from os.path import dirname
from pathlib import Path

import pytz
from crontab import CronTab
from environs import Env

from .utils import VersionDetails


env = Env()
env.read_env()

ROOT_DIR = Path(dirname(__file__)) / '..' / '..'
PROJECT_DIR = ROOT_DIR / 'project'
APPS_DIR = PROJECT_DIR / 'apps'

# Version
version_details = VersionDetails()
VERSION = version_details.version

# Env
PROJECT_ENV = env('PROJECT_ENV')
DEBUG = env.bool('DEBUG')

# Telegram
TELEGRAM_CHAT_ID = env('TELEGRAM_CHAT_ID')
TELEGRAM_TOKEN = env('TELEGRAM_TOKEN')
TELEGRAM_USERNAME = env('TELEGRAM_USERNAME')
TELEHOOKS_QUEUE_NAME = env('TELEHOOKS_QUEUE_NAME')
TELEHOOKS_HOST = env('TELEHOOKS_HOST')

# Services
OPENWEATHERMAP_URL = env('OPENWEATHERMAP_URL')

# CV
VIDEO_SRC = env.int('VIDEO_SRC')
IMSHOW = env.bool('IMSHOW')
IMAGE_RESOLUTION = tuple(env.list('IMAGE_RESOLUTION', subcast=int))
FPS = env.int('FPS')  # type: ignore

# Arduino
ARDUINO_TTY = env('ARDUINO_TTY')

# Databases
DATABASE_URL = env('DATABASE_URL')
DATABASE_DEBUG = DEBUG
_row_storage_time = env.list('STORAGE_TIME', delimiter=' ')
STORAGE_TIME = datetime.timedelta(**{_row_storage_time[1]: int(_row_storage_time[0])})

# Time
TZ = env('TZ')
PY_TZ = pytz.timezone(TZ)
time.tzset()

# Sentry
SENTRY_DSN = env('SENTRY_DSN')

# Dropbox
DROPBOX_TOKEN = env('DROPBOX_TOKEN')

# Router
ROUTER_TYPE = env('ROUTER_TYPE', validate=lambda x: x == 'mi')
ROUTER_USERNAME = env('ROUTER_USERNAME', default=None)
ROUTER_PASSWORD = env('ROUTER_PASSWORD')
ROUTER_URL = env('ROUTER_URL')

# Other
SLEEPING_TIME = tuple(env.list('SLEEPING_TIME', subcast=datetime.time.fromisoformat))
NORMAL_HUMIDITY_RANGE = env.list('NORMAL_HUMIDITY_RANGE', subcast=int)
NORMAL_TEMPERATURE_RANGE = tuple(env.list('NORMAL_TEMPERATURE_RANGE', subcast=int))
ARTIFICIAL_SUNRISE_SCHEDULES = tuple(env.list('ARTIFICIAL_SUNRISE_SCHEDULES', delimiter=';', subcast=CronTab))

# Smart devices
ZIGBEE_MQ_HOST = env('ZIGBEE_MQ_HOST')
ZIGBEE_MQ_PORT = env.int('ZIGBEE_MQ_PORT')  # type: ignore
MAIN_SMART_LAMP = env('MAIN_SMART_LAMP')
