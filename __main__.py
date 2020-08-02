#!/usr/bin/env python3
import logging
import queue
from datetime import datetime, timedelta

import schedule
import sentry_sdk
from telegram.utils.request import Request as TelegramRequest

from project import config
from project.apps import db
from project.apps.bot_implementation import handlers
from project.apps.bot_implementation.constants import BotCommands
from project.apps.bot_implementation.utils import TelegramMenu
from project.apps.common.constants import ON
from project.apps.common.state import State
from project.apps.common.storage import file_storage
from project.apps.common.threads import ThreadPool
from project.apps.messengers.base import Command, Message
from project.apps.messengers.commander import Commander
from project.apps.messengers.constants import INITED_AT, THREAD_POOL, MESSAGE_QUEUE
from project.apps.messengers.telegram import TelegramMessenger
from project.apps.messengers.utils import scheduled_task

sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    release=config.VERSION,
    environment=config.ENV,
    debug=True,
)


def main():
    logging.info('Starting app...')

    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine)

    logging.info('Removing old data...')
    file_storage.remove_old_folders()

    message_queue = queue.Queue()
    message_queue.put(Message(command=Command(name=BotCommands.STATUS)))
    message_queue.put(Message(command=Command(name=BotCommands.ARDUINO, args=(ON,))))

    state = State({
        INITED_AT: datetime.now(),
        MESSAGE_QUEUE: message_queue,
        THREAD_POOL: ThreadPool(),
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
    # scheduler.every().day.at('07:00').do(scheduled_task(state, BotCommands.REPORT))
    # scheduler.every().day.at('21:30').do(scheduled_task(state, BotCommands.GOOD_NIGHT))
    scheduler.every().day.at('23:55').do(scheduled_task(state, BotCommands.STATS))

    logging.info('Starting bot...')

    smart_bot = Commander(
        messenger=messenger,
        commands=(
            handlers.Report,
            handlers.Camera,
            handlers.Arduino,
            handlers.Menu,
            handlers.Other,
        ),
        state=state,
        scheduler=scheduler,
    )

    smart_bot.run()


if __name__ == '__main__':
    main()
