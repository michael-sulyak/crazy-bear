import datetime
import typing

from crontab import CronTab

from .. import constants
from ..base import BaseModule, Command
from ... import db
from ...arduino.constants import ArduinoSensorTypes
from ...common import doc
from ...common.utils import current_time
from ...messengers.utils import ProgressBar
from ...signals.models import Signal
from ...task_queue import IntervalTask, ScheduledTask, TaskPriorities


__all__ = (
    'Signals',
)


class Signals(BaseModule):
    doc = doc.generate_doc(
        title='Signals',
        commands=(
            doc.CommandDef(constants.BotCommands.CHECK_DB),
        ),
    )

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._check_db,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=30),
                run_immediately=False,
            ),
            IntervalTask(
                target=lambda: Signal.backup(
                    datetime_range=(
                        current_time() - datetime.timedelta(days=1),
                        current_time(),
                    ),
                ),
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(hours=2),
                run_immediately=False,
            ),
            ScheduledTask(
                target=Signal.backup,
                priority=TaskPriorities.LOW,
                crontab=CronTab('0 5 * * *'),
            ),
            ScheduledTask(
                target=db.vacuum,
                priority=TaskPriorities.LOW,
                crontab=CronTab('0 4 * * *'),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == constants.BotCommands.CHECK_DB:
            with ProgressBar(self.messenger, title='Checking DB...') as progress_bar:
                self._check_db()
                progress_bar.set(0.5, title='Run `VACUUM FULL`...')
                db.vacuum()
                progress_bar.set(1)
                self.messenger.send_message('Checking DB is finished')

            return True

        return False

    @staticmethod
    def _check_db() -> None:
        now = current_time()

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

        with db.db_session().begin():
            db.db_session().query(Signal).filter(
                Signal.type == constants.TASK_QUEUE_DELAY,
                Signal.received_at <= now - datetime.timedelta(days=2),
            ).delete()

        datetime_range = (
            now - datetime.timedelta(hours=3),
            now - datetime.timedelta(minutes=5),
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
            Signal.compress_by_time(
                item,
                datetime_range=datetime_range,
            )

            Signal.compress(
                item,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )

        db.db_session().query(Signal).filter(
            Signal.type.notin_(all_signals),
        ).delete()
