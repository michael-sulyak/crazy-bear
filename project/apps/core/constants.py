from emoji.core import emojize

from ..common.constants import OFF, ON


CPU_TEMPERATURE = 'cpu_temperature'
WEATHER_TEMPERATURE = 'weather_temperature'
WEATHER_HUMIDITY = 'weather_humidity'
RAM_USAGE = 'ram_usage'
FREE_DISK_SPACE = 'free_disk_space'
TASK_QUEUE_DELAY = 'task_queue_delay'
USER_IS_CONNECTED_TO_ROUTER = 'user_is_connected_to_router'
USER_IS_AT_HOME = 'user_is_at_home'
CONNECTED_DEVICES_TO_ROUTER = 'connected_devices_to_router'

AUTO_SECURITY_IS_ENABLED = 'auto_security_is_enabled'
USE_CAMERA = 'use_camera'
VIDEO_RECORDING_IS_ENABLED = 'video_recording_is_enabled'
CAMERA_IS_AVAILABLE = 'camera_is_available'
SECURITY_IS_ENABLED = 'security_is_enabled'
VIDEO_SECURITY_IS_ENABLED = 'video_security'
CURRENT_FPS = 'current_fps'
PHOTO = 'photo'
RECOMMENDATION_SYSTEM_IS_ENABLED = 'recommendation_system_is_enabled'
MAIN_LAMP_IS_ON = 'main_lamp_is_on'
MENU_PAGES_MAP = 'menu_pages_map'


class BotCommands:
    REPORT = '/report'

    TAKE_PICTURE = '/take_picture'

    SECURITY = '/security'
    CAMERA = '/camera'

    STATUS = '/status'
    STATS = '/stats'
    LAMP = '/lamp'

    TO = '/to'
    RAW_WIFI_DEVICES = '/raw_wifi_devices'
    HELP = '/help'
    COMPRESS_DB = '/compress_db'
    DB_STATS = '/db_stats'
    RETURN = '/return'
    TIMER = '/timer'


class PrettyBotCommands:
    STATUS = f'{emojize(":page_facing_up:")} Status'
    SHORT_STATS = f'{emojize(":bar_chart:")} Short stats'
    SECURITY_ON = f'{emojize(":police_officer:")} Security ON'
    SECURITY_OFF = f'{emojize(":police_officer:")} Security OFF'
    SECURITY_AUTO_ON = f'{emojize(":robot:")} Auto security ON'
    SECURITY_AUTO_OFF = f'{emojize(":robot:")} Auto security OFF'
    ALL_FUNCS = f'{emojize(":hammer_and_wrench:")} All utils'
    LAMP = f'{emojize(":light_bulb:")} Lamp'


BOT_COMMAND_ALIASES = {
    PrettyBotCommands.STATUS: BotCommands.STATUS,
    PrettyBotCommands.SHORT_STATS: f'{BotCommands.STATS} -s',
    PrettyBotCommands.SECURITY_ON: f'{BotCommands.SECURITY} {ON}',
    PrettyBotCommands.SECURITY_OFF: f'{BotCommands.SECURITY} {OFF}',
    PrettyBotCommands.SECURITY_AUTO_ON: f'{BotCommands.SECURITY} auto {ON}',
    PrettyBotCommands.SECURITY_AUTO_OFF: f'{BotCommands.SECURITY} auto {OFF}',
    PrettyBotCommands.ALL_FUNCS: f'{BotCommands.TO} all_funcs',
    PrettyBotCommands.LAMP: f'{BotCommands.TO} lamp',
}


class MotionTypeSources:
    SENSORS = 'sensors'
    VIDEO = 'video'
