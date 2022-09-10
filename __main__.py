#!/usr/bin/env python3
import datetime
import logging
import signal

import sentry_sdk
from crontab import CronTab
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration

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
from project.apps.task_queue import TaskPriorities
from project.apps.task_queue.dto import DelayedTask, ScheduledTask


logging_level = logging.DEBUG if config.DEBUG else logging.INFO
logging.basicConfig(level=logging_level)


def get_traces_sampler(sampling_context: dict) -> float:
    op = sampling_context['transaction_context']['op']

    if op == 'cmd':
        return 0.1

    if op == 'task':
        return 0.05

    if op == 'repeatabletask':
        return 0.0005

    if op == 'delayedtask':
        return 0.005

    if op == 'intervaltask':
        return 0.001

    if op == 'scheduledtask':
        return 0.05

    return 0.25


sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    release=config.VERSION,
    environment=config.PROJECT_ENV,
    debug=config.DEBUG,
    integrations=(
        LoggingIntegration(
            level=logging_level,
            event_level=logging.ERROR,
        ),
        ThreadingIntegration(
            propagate_hub=True,
        ),
        SqlalchemyIntegration(),
    ),
    traces_sampler=get_traces_sampler,
)


def handle_sigterm(*args) -> None:
    raise Shutdown


signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)


def main():
    logging.info('Starting app...')

    init_settings_for_plt()

    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine, checkfirst=True)

    state = State({
        INITED_AT: datetime.datetime.now(),
    })

    messenger = TelegramMessenger(
        default_reply_markup=TelegramMenu(state=state),
    )

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
            modules.Signals,
            modules.WiFiDevices,
            modules.SmartLampController,
            modules.ExtraCommands,
        ),
        state=state,
    )

    initial_tasks = (
        DelayedTask(
            target=file_storage.remove_old_folders,
            priority=TaskPriorities.LOW,
            delay=datetime.timedelta(seconds=30),
        ),
        ScheduledTask(
            target=file_storage.remove_old_folders,
            priority=TaskPriorities.LOW,
            crontab=CronTab('0 1 * * *'),
        ),
    )

    for initial_task in initial_tasks:
        commander.task_queue.put_task(initial_task)

    initial_commands = (
        Command(name=BotCommands.ARDUINO, args=(ON,)),
        Command(name=BotCommands.SECURITY, args=(AUTO, ON,)),
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
