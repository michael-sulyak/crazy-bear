#!/usr/bin/env python3
import logging
import signal
from datetime import datetime

import schedule
import sentry_sdk
from telegram.utils.request import Request as TelegramRequest

from project import config
from project.apps import db
from project.apps.core import modules
from project.apps.messengers.utils import TelegramMenu
from project.apps.common.constants import AUTO, ON
from project.apps.common.state import State
from project.apps.common.storage import file_storage
from project.apps.core.base import Command, Message
from project.apps.core.commander import Commander
from project.apps.messengers.constants import BotCommands, INITED_AT
from project.apps.messengers.telegram import TelegramMessenger


logging.basicConfig(level='DEBUG' if config.DEBUG else 'INFO')


sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    release=config.VERSION,
    environment=config.PROJECT_ENV,
    debug=config.DEBUG,
)


def handle_sigterm(*args):
    raise KeyboardInterrupt()


signal.signal(signal.SIGTERM, handle_sigterm)


def main():
    logging.info('Starting app...')

    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine)

    logging.info('Removing old data...')
    file_storage.remove_old_folders()

    state = State({
        INITED_AT: datetime.now(),
    })

    if config.PROXY_URL:
        logging.info('Found proxy for Telegram.')

        request = TelegramRequest(
            proxy_url=config.PROXY_URL,
            urllib3_proxy_kwargs={
                'username': config.PROXY_USERNAME,
                'password': config.PROXY_PASSWORD,
            },
        )
    else:
        logging.info('Not found proxy for Telegram.')
        request = None

    messenger = TelegramMessenger(
        request=request,
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
        ),
        state=state,
        scheduler=scheduler,
    )

    initial_commands = (
        Command(name=BotCommands.STATUS),
        Command(name=BotCommands.ARDUINO, args=(ON,)),
        Command(name=BotCommands.SECURITY, args=(AUTO, ON,)),
        Command(name=BotCommands.RECOMMENDATION_SYSTEM, args=(ON,)),
    )

    for command in initial_commands:
        commander.message_queue.put(Message(command=command))

    try:
        commander.run()
    finally:
        db.close_db_session()


if __name__ == '__main__':
    main()
