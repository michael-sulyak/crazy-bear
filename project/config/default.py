import time
from os.path import dirname
from pathlib import Path

import pytz

from .utils import VersionConfig, env


BASE_DIR = Path(dirname(__file__)) / '..' / '..'
PROJECT_DIR = BASE_DIR / 'project'
APPS_DIR = PROJECT_DIR / 'apps'


# Version
version_manager = VersionConfig()
VERSION = version_manager.version

# Env
ENV = env('ENV')

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
IMAGE_RESOLUTION = (env.int('IMAGE_RESOLUTION_X'), env.int('IMAGE_RESOLUTION_Y'),)
FPS = env.int('FPS')

# Arduino
ARDUINO_TTY = env('ARDUINO_TTY')

# Databases
DATABASE_URL = 'sqlite:///:memory:'
DATABASE_DEBUG = True

# Time
TZ = env('TZ')
PY_TIME_ZONE = pytz.timezone(TZ)
time.tzset()

# Sentry
SENTRY_DSN = env('SENTRY_DSN')

# Dropbox
DROPBOX_TOKEN = env('DROPBOX_TOKEN')
