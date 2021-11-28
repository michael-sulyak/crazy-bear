#!/usr/bin/env python3
import logging
import signal
from datetime import datetime

import schedule
import sentry_sdk

from project import config
from project.apps import db
from project.apps.common.constants import AUTO, INITED_AT, ON
from project.apps.common.exceptions import Shutdown
from project.apps.common.state import State
from project.apps.common.storage import file_storage
from project.apps.common.utils import init_settings_for_plt
from project.apps.core import modules
from project.apps.core.base import Command, Message
from project.apps.core.commander import Commander
from project.apps.core.constants import BotCommands
from project.apps.core.modules import TelegramMenu
from project.apps.messengers.telegram import TelegramMessenger


logging.basicConfig(level='DEBUG' if config.DEBUG else 'INFO')

sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    release=config.VERSION,
    environment=config.PROJECT_ENV,
    debug=config.DEBUG,
)


def handle_sigterm(*args):
    raise Shutdown()


signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)


def main():
    logging.info('Starting app...')

    init_settings_for_plt()

    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine)

    logging.info('Removing old data...')
    file_storage.remove_old_folders()

    state = State({
        INITED_AT: datetime.now(),
    })

    messenger = TelegramMessenger(
        default_reply_markup=TelegramMenu(state=state),
    )

    scheduler = schedule.Scheduler()
    scheduler.every().day.at('01:00').do(file_storage.remove_old_folders)

    logging.info('Starting bot...')

    commander = Commander(
        messenger=messenger,
        module_classes=(
            modules.Camera,
            modules.Arduino,
            modules.Menu,
            modules.Report,
            modules.AutoSecurity,
            modules.Router,
            modules.RecommendationSystem,
            modules.Signals,
            modules.Devices,
        ),
        state=state,
        scheduler=scheduler,
    )

    initial_commands = (
        Command(name=BotCommands.ARDUINO, args=(ON,)),
        Command(name=BotCommands.SECURITY, args=(AUTO, ON,)),
        Command(name=BotCommands.RECOMMENDATION_SYSTEM, args=(ON,)),
        Command(name=BotCommands.STATUS),
    )

    for command in initial_commands:
        commander.message_queue.put(Message(command=command))

    try:
        commander.run()
    finally:
        db.close_db_session()


if __name__ == '__main__':
    main()
