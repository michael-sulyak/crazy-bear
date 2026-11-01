from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .constants import BOT_COMMAND_ALIASES, BotCommands, PrettyBotCommands as Buttons


# Each action belongs to a panel and resolves to a fixed, existing command.
# Client callback data is never interpreted as executable command text.
PANEL_ACTIONS = {
    'lamp_on': ('lamp', BOT_COMMAND_ALIASES[Buttons.LAMP_ON]),
    'lamp_off': ('lamp', BOT_COMMAND_ALIASES[Buttons.LAMP_OFF]),
    'lamp_night': ('lamp', BOT_COMMAND_ALIASES[Buttons.LAMP_DIM]),
    'lamp_dimmer': ('lamp', BOT_COMMAND_ALIASES[Buttons.LAMP_DIMMER]),
    'lamp_brighter': ('lamp', BOT_COMMAND_ALIASES[Buttons.LAMP_BRIGHTER]),
    'lamp_warm': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_WARM]),
    'lamp_cool': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_COOL]),
    'lamp_white': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_WHITE]),
    'lamp_yellow': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_YELLOW]),
    'lamp_blue': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_BLUE]),
    'lamp_green': ('lamp_colors', BOT_COMMAND_ALIASES[Buttons.LAMP_GREEN]),
    'security_on': ('security', BOT_COMMAND_ALIASES[Buttons.SECURITY_ON]),
    'security_off': ('security', BOT_COMMAND_ALIASES[Buttons.SECURITY_OFF]),
    'auto_on': ('security', BOT_COMMAND_ALIASES[Buttons.SECURITY_AUTO_ON]),
    'auto_off': ('security', BOT_COMMAND_ALIASES[Buttons.SECURITY_AUTO_OFF]),
    'heat_2': ('heating', BOT_COMMAND_ALIASES[Buttons.HEATING_PAUSE_2]),
    'heat_4': ('heating', BOT_COMMAND_ALIASES[Buttons.HEATING_PAUSE_4]),
    'heat_resume': ('heating', BOT_COMMAND_ALIASES[Buttons.HEATING_RESUME]),
    'heat_boost_2': ('heating', BOT_COMMAND_ALIASES[Buttons.HEATING_BOOST_2]),
    'heat_boost_4': ('heating', BOT_COMMAND_ALIASES[Buttons.HEATING_BOOST_4]),
    'camera_on': ('camera', BOT_COMMAND_ALIASES[Buttons.CAMERA_ON]),
    'camera_off': ('camera', BOT_COMMAND_ALIASES[Buttons.CAMERA_OFF]),
    'camera_photo': ('camera', BOT_COMMAND_ALIASES[Buttons.CAMERA_PHOTO]),
    'record_on': ('camera', BOT_COMMAND_ALIASES[Buttons.CAMERA_RECORD_ON]),
    'record_off': ('camera', BOT_COMMAND_ALIASES[Buttons.CAMERA_RECORD_OFF]),
    'history_1': ('history', BOT_COMMAND_ALIASES[Buttons.HISTORY_1]),
    'history_6': ('history', BOT_COMMAND_ALIASES[Buttons.HISTORY_6]),
    'history_24': ('history', BOT_COMMAND_ALIASES[Buttons.HISTORY_24]),
    'history_7d': ('history', BOT_COMMAND_ALIASES[Buttons.HISTORY_7D]),
    'history_full': ('history', BotCommands.STATS),
    'commands': ('all_funcs', BOT_COMMAND_ALIASES[Buttons.ALL_COMMANDS]),
    'help': ('all_funcs', BotCommands.HELP),
    'wifi': ('system', BotCommands.RAW_WIFI_DEVICES),
    'db_stats': ('system', BotCommands.DB_STATS),
}

CALLBACK_COMMANDS = {
    'ui:status': BotCommands.STATUS,
    'ui:commands': f'{BotCommands.HELP} commands',
    **{f'ui:{page}': f'{BotCommands.TO} {page}' for page in (
        'lamp', 'lamp_colors', 'security', 'heating', 'history',
        'all_funcs', 'camera', 'system', 'confirm_compress',
    )},
    **{f'act:{action}': f'/panel {action}' for action in PANEL_ACTIONS},
    'act:confirm_compress': '/panel confirm_compress',
}

BUTTON_CALLBACKS = {
    label: f'act:{action}'
    for action, (_, command) in PANEL_ACTIONS.items()
    for label, alias in BOT_COMMAND_ALIASES.items()
    if alias == command
}
BUTTON_CALLBACKS.update({
    Buttons.STATUS: 'ui:status',
    Buttons.LAMP: 'ui:lamp',
    Buttons.LAMP_COLORS: 'ui:lamp_colors',
    Buttons.SECURITY: 'ui:security',
    Buttons.HEATING: 'ui:heating',
    Buttons.HISTORY: 'ui:history',
    Buttons.ALL_FUNCS: 'ui:all_funcs',
    Buttons.CAMERA: 'ui:camera',
    Buttons.SYSTEM: 'ui:system',
})

COMMAND_MENU = (
    # BotCommand('status', 'Live readings and navigation keyboard'),
    # BotCommand('start', 'Restore navigation and show status'),
    # BotCommand('stats', 'History for the last 24 h'),
    # BotCommand('help', 'Quick guide and command reference'),
)


def status_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔄 Refresh', callback_data='ui:status')],
    ])
