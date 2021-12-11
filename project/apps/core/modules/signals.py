import datetime
import typing

from crontab import CronTab
from sqlalchemy import func as sa_func

from .. import constants
from ..base import BaseModule, Command
from ..constants import BotCommands
from ... import db
from ...arduino.constants import ArduinoSensorTypes
from ...common.utils import current_time
from ...signals.models import Signal
from ...task_queue import IntervalTask, ScheduledTask, TaskPriorities


__all__ = (
    'Signals',
)


class Signals(BaseModule):
    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._check_db,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=30),
                run_immediately=False,
            ),
            IntervalTask(
                target=Signal.backup,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(hours=2),
                run_immediately=False,
            ),
            ScheduledTask(
                target=db.vacuum,
                priority=TaskPriorities.LOW,
                crontab=CronTab('0 4 * * *'),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CHECK_DB:
            self._check_db()
            self.messenger.send_message('Checked. Run `VACUUM FULL`')
            self.messenger.start_typing()
            db.vacuum()
            self.messenger.send_message('`VACUUM FULL` is finished')
            return True

        return False

    @staticmethod
    def _check_db() -> None:
        for_compress = (
            constants.USER_IS_CONNECTED_TO_ROUTER,
            constants.TASK_QUEUE_DELAY,
            ArduinoSensorTypes.PIR_SENSOR,
        )

        for_compress_by_time = (
            constants.WEATHER_TEMPERATURE,
            constants.WEATHER_HUMIDITY,
            constants.CPU_TEMPERATURE,
            constants.RAM_USAGE,
            ArduinoSensorTypes.TEMPERATURE,
            ArduinoSensorTypes.HUMIDITY,
        )

        all_signals = {*for_compress, *for_compress_by_time}

        Signal.clear(all_signals)

        now = current_time()

        datetime_range = (
            now - datetime.timedelta(hours=6),
            now - datetime.timedelta(minutes=5),
        )

        Signal.compress_by_time(
            ArduinoSensorTypes.PIR_SENSOR,
            datetime_range=datetime_range,
            aggregate_function=sa_func.max,
        )

        for item in for_compress:
            if item == ArduinoSensorTypes.PIR_SENSOR:
                approximation_value = 20
            elif item in (ArduinoSensorTypes.TEMPERATURE, ArduinoSensorTypes.HUMIDITY,):
                approximation_value = 0.1
            else:
                approximation_value = 0

            Signal.compress(
                item,
                datetime_range=datetime_range,
                approximation_value=approximation_value,
                approximation_time=datetime.timedelta(minutes=10),
            )

        for item in for_compress_by_time:
            Signal.compress_by_time(item, datetime_range=datetime_range)
            Signal.compress(item, datetime_range=datetime_range)

        db.db_session().query(Signal).filter(
            Signal.type.notin_(all_signals),
        ).delete()
