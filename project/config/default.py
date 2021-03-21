import datetime
import time
from os.path import dirname
from pathlib import Path

import pytz

from .utils import VersionConfig, env


BASE_DIR = Path(dirname(__file__)) / '..' / '..'
PROJECT_DIR = BASE_DIR / 'project'
APPS_DIR = PROJECT_DIR / 'apps'


# Version
version_config = VersionConfig()
VERSION = version_config.version

# Env
PROJECT_ENV = env('PROJECT_ENV')
DEBUG = env.bool('DEBUG')

# Telegram
TELEGRAM_CHAT_ID = env('TELEGRAM_CHAT_ID')
TELEGRAM_TOKEN = env('TELEGRAM_TOKEN')
TELEGRAM_USERNAME = env('TELEGRAM_USERNAME')

# Proxy for telegram
PROXY_URL = env('PROXY_URL')
PROXY_USERNAME = env('PROXY_USERNAME')
PROXY_PASSWORD = env('PROXY_PASSWORD')

# Services
OPENWEATHERMAP_URL = env('OPENWEATHERMAP_URL')

# CV
VIDEO_SRC = env.int('VIDEO_SRC')
IMSHOW = env.bool('IMSHOW')
IMAGE_RESOLUTION = env.tuple('IMAGE_RESOLUTION', value_type=int)
FPS = env.int('FPS')

# Arduino
ARDUINO_TTY = env('ARDUINO_TTY')

# Databases
DATABASE_URL = env('DATABASE_URL')
DATABASE_DEBUG = DEBUG
STORAGE_TIME = datetime.timedelta(hours=env.int('STORAGE_TIME'))

# Time
TZ = env('TZ')
PY_TIME_ZONE = pytz.timezone(TZ)
time.tzset()

# Sentry
SENTRY_DSN = env('SENTRY_DSN')

# Dropbox
DROPBOX_TOKEN = env('DROPBOX_TOKEN')

# Router
ROUTER_USERNAME = env('ROUTER_USERNAME')
ROUTER_PASSWORD = env('ROUTER_PASSWORD')
ROUTER_URL = env('ROUTER_URL')
ROUTER_USER_MAC_ADDRESSES = env.frozenset('ROUTER_USER_MAC_ADDRESSES')

# Other
SLEEP_HOURS = env.tuple('SLEEP_HOURS', value_type=int)
