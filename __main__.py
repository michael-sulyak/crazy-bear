import datetime
import logging
import signal

import sentry_sdk
from crontab import CronTab
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration

from libs.messengers.telegram import TelegramMessenger
from libs.task_queue import DelayedTask, ScheduledTask, TaskPriorities
from libs.zigbee.base import ZigBee
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from libs.zigbee.lamps.life_control import LCSmartLamp
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
from project.apps.core.utils.messages import process_telegram_message


log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging_level = logging.DEBUG if config.DEBUG else logging.INFO
logging.basicConfig(level=logging_level, format=log_format)
logging.getLogger('https').setLevel(logging.WARNING)


def get_traces_sampler(sampling_context: dict) -> float:
    op = sampling_context['transaction_context']['op']

    if op == 'cmd':
        value = 0.1
    elif op == 'task':
        value = 0.05
    elif op == 'repeatabletask':
        value = 0.0005
    elif op == 'delayedtask':
        value = 0.005
    elif op == 'intervaltask':
        value = 0.001
    elif op == 'scheduledtask':
        value = 0.05
    else:
        value = 0.25

    return value


def main() -> None:
    logging.info('Starting app...')

    def shutdown(*args) -> None:
        logging.info('Got signal to shutdown.')
        # commander.close()
        raise Shutdown

    for signal_name in (
        'SIGINT',
        'SIGTERM',
    ):
        signal.signal(getattr(signal, signal_name), shutdown)

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

    init_settings_for_plt()

    logging.info('Creating database...')
    db.Base.metadata.create_all(db.db_engine, checkfirst=True)

    logging.info('Setting up commander...')

    state = State(
        {
            INITED_AT: datetime.datetime.now(),
        },
    )

    messenger = TelegramMessenger(
        message_handler=process_telegram_message,
        default_reply_markup=TelegramMenu(state=state),
    )

    zig_bee = ZigBee(
        mq_host=config.ZIGBEE_MQ_HOST,
        mq_port=config.ZIGBEE_MQ_PORT,
    )

    commander = Commander(
        messenger=messenger,
        zig_bee=zig_bee,
        state=state,
        module_classes=(
            modules.Camera,
            modules.Menu,
            modules.Report,
            modules.Security,
            modules.Router,
            modules.Signals,
            modules.ZigBeeController,
            modules.LampControllerInBedroom,
            modules.Utils,
        ),
        smart_devices=(
            LCSmartLamp(config.SmartDeviceNames.MAIN_SMART_LAMP, zig_bee=zig_bee),
            ZigBeeDeviceWithOnlyState(config.SmartDeviceNames.WATER_LEAK_SENSOR_WC_OPEN, zig_bee=zig_bee),
            ZigBeeDeviceWithOnlyState(config.SmartDeviceNames.TEMP_HUM_SENSOR_WORK_ROOM, zig_bee=zig_bee),
            ZigBeeDeviceWithOnlyState(config.SmartDeviceNames.MOTION_SENSOR_HALLWAY, zig_bee=zig_bee),
            ZigBeeDeviceWithOnlyState(config.SmartDeviceNames.DOOR_SENSOR_NARNIA, zig_bee=zig_bee),
        ),
    )

    initial_tasks = (
        DelayedTask(
            target=file_storage.remove_old_folders,
            priority=TaskPriorities.LOW,
            delay=datetime.timedelta(minutes=1),
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
        Command(
            name=BotCommands.SECURITY,
            args=(
                AUTO,
                ON,
            ),
        ),
        Command(name=BotCommands.STATUS),
    )

    for command in initial_commands:
        commander.message_queue.put(Message(command=command))

    logging.info('Running commander...')

    try:
        commander.run()
    finally:
        db.close_db_session()


if __name__ == '__main__':
    main()
