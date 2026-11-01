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
LAST_CRITICAL_SITUATION_OCCURRED_AT = 'last_critical_situation_occurred_at'

AIR_MONITOR_STATE = 'air_monitor_state'
AIR_MONITOR_TEMPERATURE = 'air_monitor_temperature'
AIR_MONITOR_HUMIDITY = 'air_monitor_humidity'
AIR_MONITOR_CO2 = 'air_monitor_co2'
AIR_MONITOR_PM25 = 'air_monitor_pm25'
AIR_MONITOR_PM10 = 'air_monitor_pm10'

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
HEATING_PAUSED_UNTIL = 'heating_paused_until'
HEATING_BOOSTED_UNTIL = 'heating_boosted_until'
MENU_PAGES_MAP = 'menu_pages_map'


class BotCommands:
    START = '/start'
    HOME = '/home'

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
    SECURITY_ON = '🛡️ Enable security'
    SECURITY_OFF = '🛡️ Disable security'
    SECURITY_AUTO_ON = '🤖 Enable auto security'
    SECURITY_AUTO_OFF = '🤖 Disable auto security'
    ALL_FUNCS = '🧰 More'
    LAMP = f'{emojize(":light_bulb:")} Lamp'
    HOME = '🏠 Home'
    BACK = '⬅️ Back'
    HELP = '❓ Help'
    ALL_COMMANDS = '📖 All commands'
    SECURITY = '🛡️ Security'
    CAMERA = '📷 Camera'
    HEATING = '🌡️ Heating'
    HISTORY = '📊 History'
    HISTORY_1 = '🕐 Last 1 h'
    HISTORY_6 = '🕕 Last 6 h'
    HISTORY_24 = '📅 Last 24 h'
    HISTORY_7D = '🗓️ Last 7 days'
    LAMP_COLORS = '🎨 Colors'
    SYSTEM = '⚙️ System'
    STATS = '📈 Full history'
    WIFI = '📶 WiFi devices'
    DB_STATS = '💾 Database usage'
    LAMP_ON = '💡 Turn on'
    LAMP_OFF = '🌑 Turn off'
    LAMP_DIM = '🌙 Night light'
    LAMP_BRIGHTER = '🔆 Brighter'
    LAMP_DIMMER = '🔅 Dimmer'
    LAMP_WARM = '🕯️ Warm light'
    LAMP_COOL = '❄️ Cool light'
    LAMP_WHITE = '⚪ White'
    LAMP_YELLOW = '🟡 Yellow'
    LAMP_BLUE = '🔵 Blue'
    LAMP_GREEN = '🟢 Green'
    CAMERA_ON = '📷 Enable camera'
    CAMERA_OFF = '📷 Disable camera'
    CAMERA_PHOTO = '📸 Take photo'
    CAMERA_RECORD_ON = '⏺️ Start recording'
    CAMERA_RECORD_OFF = '⏹️ Stop recording'
    HEATING_PAUSE_2 = '⏸️ Pause for 2 h'
    HEATING_PAUSE_4 = '⏸️ Pause for 4 h'
    HEATING_RESUME = '▶️ Resume schedule'
    HEATING_BOOST_2 = '🔥 30 °C for 2 h'
    HEATING_BOOST_4 = '🔥 30 °C for 4 h'


BOT_COMMAND_ALIASES = {
    PrettyBotCommands.STATUS: BotCommands.STATUS,
    PrettyBotCommands.SHORT_STATS: f'{BotCommands.STATS} -s',
    PrettyBotCommands.SECURITY_ON: f'{BotCommands.SECURITY} {ON}',
    PrettyBotCommands.SECURITY_OFF: f'{BotCommands.SECURITY} {OFF}',
    PrettyBotCommands.SECURITY_AUTO_ON: f'{BotCommands.SECURITY} auto {ON}',
    PrettyBotCommands.SECURITY_AUTO_OFF: f'{BotCommands.SECURITY} auto {OFF}',
    PrettyBotCommands.ALL_FUNCS: f'{BotCommands.TO} all_funcs',
    PrettyBotCommands.LAMP: f'{BotCommands.TO} lamp',
    PrettyBotCommands.HOME: BotCommands.HOME,
    PrettyBotCommands.BACK: BotCommands.RETURN,
    PrettyBotCommands.HELP: BotCommands.HELP,
    PrettyBotCommands.ALL_COMMANDS: f'{BotCommands.HELP} commands',
    PrettyBotCommands.SECURITY: f'{BotCommands.TO} security',
    PrettyBotCommands.CAMERA: f'{BotCommands.TO} camera',
    PrettyBotCommands.HEATING: f'{BotCommands.TO} heating',
    PrettyBotCommands.HISTORY: f'{BotCommands.TO} history',
    PrettyBotCommands.HISTORY_1: f'{BotCommands.STATS} 1 hours -s',
    PrettyBotCommands.HISTORY_6: f'{BotCommands.STATS} 6 hours -s',
    PrettyBotCommands.HISTORY_24: f'{BotCommands.STATS} 24 hours -s',
    PrettyBotCommands.HISTORY_7D: f'{BotCommands.STATS} 7 days -s',
    PrettyBotCommands.LAMP_COLORS: f'{BotCommands.TO} lamp_colors',
    PrettyBotCommands.SYSTEM: f'{BotCommands.TO} system',
    PrettyBotCommands.STATS: BotCommands.STATS,
    PrettyBotCommands.WIFI: BotCommands.RAW_WIFI_DEVICES,
    PrettyBotCommands.DB_STATS: BotCommands.DB_STATS,
    PrettyBotCommands.LAMP_ON: f'{BotCommands.LAMP} {ON}',
    PrettyBotCommands.LAMP_OFF: f'{BotCommands.LAMP} {OFF}',
    PrettyBotCommands.LAMP_DIM: f'{BotCommands.LAMP} {ON} 5',
    PrettyBotCommands.LAMP_BRIGHTER: f'{BotCommands.LAMP} increase_brightness',
    PrettyBotCommands.LAMP_DIMMER: f'{BotCommands.LAMP} decrease_brightness',
    PrettyBotCommands.LAMP_WARM: f'{BotCommands.LAMP} color_temp 333',
    PrettyBotCommands.LAMP_COOL: f'{BotCommands.LAMP} color_temp 167',
    PrettyBotCommands.LAMP_WHITE: f'{BotCommands.LAMP} color white',
    PrettyBotCommands.LAMP_YELLOW: f'{BotCommands.LAMP} color yellow',
    PrettyBotCommands.LAMP_BLUE: f'{BotCommands.LAMP} color blue',
    PrettyBotCommands.LAMP_GREEN: f'{BotCommands.LAMP} color green',
    PrettyBotCommands.CAMERA_ON: f'{BotCommands.CAMERA} {ON}',
    PrettyBotCommands.CAMERA_OFF: f'{BotCommands.CAMERA} {OFF}',
    PrettyBotCommands.CAMERA_PHOTO: f'{BotCommands.CAMERA} photo',
    PrettyBotCommands.CAMERA_RECORD_ON: f'{BotCommands.CAMERA} record {ON}',
    PrettyBotCommands.CAMERA_RECORD_OFF: f'{BotCommands.CAMERA} record {OFF}',
    PrettyBotCommands.HEATING_PAUSE_2: '/trv disable 2',
    PrettyBotCommands.HEATING_PAUSE_4: '/trv disable 4',
    PrettyBotCommands.HEATING_RESUME: '/trv enable',
    PrettyBotCommands.HEATING_BOOST_2: '/trv boost 2',
    PrettyBotCommands.HEATING_BOOST_4: '/trv boost 4',
}


class MotionTypeSources:
    SENSORS = 'sensors'
    VIDEO = 'video'
