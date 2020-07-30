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
from project.apps.bot_implementation.constants import BotCommands, TelegramMenu
from project.apps.common.state import State
from project.apps.common.storage import file_storage
from project.apps.common.threads import ThreadPool
from project.apps.messengers.base import MessengerCommand, MessengerUpdate
from project.apps.messengers.commander import Commander
from project.apps.messengers.constants import INITED_AT, THREAD_POOL, UPDATES
from project.apps.messengers.telegram import TelegramMessenger
from project.apps.messengers.utils import scheduled_task

sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    release=config.VERSION,
    environment=config.ENV,
    debug=True,
)


def main():
    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine)

    logging.info('Removing old data...')
    file_storage.remove_old_folders()

    logging.info('Starting app...')

    updates = queue.Queue()
    updates.put(MessengerUpdate(command=MessengerCommand(name=BotCommands.STATUS)))
    updates.put(MessengerUpdate(command=MessengerCommand(name=BotCommands.ARDUINO, args=('on',))))

    state = State({
        INITED_AT: datetime.now(),
        UPDATES: updates,
        THREAD_POOL: ThreadPool(timedelta_for_sync=timedelta(seconds=20)),
    })

    if config.PROXY_URL:
        request = TelegramRequest(
            proxy_url=config.PROXY_URL,
            urllib3_proxy_kwargs={
                'username': config.PROXY_USERNAME,
                'password': config.PROXY_PASSWORD,
            },
        )
    else:
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
