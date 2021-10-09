import datetime
import logging

import schedule
import typing

from .. import constants
from ..base import BaseModule, Command
from ... import db
from ...arduino.constants import ArduinoSensorTypes
from ..constants import BotCommands
from ...signals.models import Signal
from ...task_queue import TaskPriorities


__all__ = (
    'Signals',
)


class Signals(BaseModule):
    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(30).minutes.do(
                self.unique_task_queue.push,
                self._check_db,
                priority=TaskPriorities.LOW,
            ),
            scheduler.every(2).hours.do(
                self.unique_task_queue.push,
                Signal.backup,
                priority=TaskPriorities.LOW,
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CHECK_DB:
            self._check_db()
            self.messenger.send_message('Checked')
            return True

        return False

    @staticmethod
    def _check_db() -> None:
        logging.debug('Signals._check_data()')

        for_compress = (
            constants.USER_IS_CONNECTED_TO_ROUTER,
            constants.TASK_QUEUE_DELAY,
            ArduinoSensorTypes.PIR_SENSOR,
        )

        for_aggregated_compress = (
            constants.WEATHER_TEMPERATURE,
            constants.WEATHER_HUMIDITY,
            constants.CPU_TEMPERATURE,
            constants.RAM_USAGE,
            ArduinoSensorTypes.TEMPERATURE,
            ArduinoSensorTypes.HUMIDITY,
        )

        all_signals = (*for_compress, *for_aggregated_compress,)

        Signal.clear(all_signals)

        now = datetime.datetime.now()

        date_range = (
            now - datetime.timedelta(hours=6),
            now - datetime.timedelta(minutes=5),
        )

        for item in for_compress:
            Signal.compress(
                item,
                date_range=date_range,
                approximation=20 if item == ArduinoSensorTypes.PIR_SENSOR else 0,
            )

        for item in for_aggregated_compress:
            Signal.aggregated_compress(item, date_range=date_range)
            Signal.compress(item, date_range=date_range)

        with db.db_session().transaction:
            db.db_session().query(Signal).filter(
                Signal.type.notin_(all_signals),
            ).delete()

        db.vacuum()
