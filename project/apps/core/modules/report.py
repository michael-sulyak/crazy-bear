import datetime
import logging
import threading
import typing

from emoji import emojize
from sqlalchemy import text

from libs.casual_utils.time import get_current_time
from libs.messengers.utils import ProgressBar, escape_markdown
from libs.task_queue import IntervalTask, TaskPriorities
from .. import events
from ..base import BaseModule, Command
from ..utils.reports import ShortTextReport
from ... import db
from ...common import interface
from ...common.exceptions import Shutdown
from ...common.utils import (
    convert_params_to_date_range, get_weather, is_sleep_hours,
)
from ...core import constants
from ...signals.models import Signal


@interface.module(
    title='Report',
    description=(
        'The module provides a short report with needed data.'
    ),
)
class Report(BaseModule):
    _stats_flags_map = {
        'a': 'arduino',
        'e': 'extra_data',
        'i': 'inner_stats',
        'r': 'router_usage',
    }
    _lock_for_status: threading.RLock
    _message_id_for_status: typing.Any = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock_for_status = threading.RLock()

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._update_status,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=1),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        with self._lock_for_status:
            self._message_id_for_status = None

        return super().process_command(command)

    @interface.command(
        constants.BotCommands.STATS,
        flags=(
            interface.Flag('s'),
        ),
    )
    @interface.command(
        constants.BotCommands.STATS,
        interface.Value('number', python_type=int),
        interface.Choices('days', 'hours', 'minutes', 'seconds'),
        flags=(
            interface.Flag('s'),
        ),
    )
    def _send_stats(self, command: Command) -> None:
        delta_type = str(command.get_second_arg('hours', skip_flags=True))
        delta_value = int(command.get_first_arg('24', skip_flags=True))

        date_range = convert_params_to_date_range(
            delta_type=delta_type,
            delta_value=delta_value,
        )

        flags = command.get_cleaned_flags()

        if not flags or flags == {'f'}:
            flags = self._stats_flags_map.keys()

        if flags == {'s'}:
            flags = {'a', 'e', 'r'}

        events.request_for_statistics.pipe(
            self._pipe_for_collecting_stats,
            date_range=date_range,
            components={self._stats_flags_map[flag] for flag in flags},
        )

    @interface.command(constants.BotCommands.HELP)
    def _send_help(self) -> None:
        docs = sorted(events.getting_doc.process()[0], key=lambda x: x.title)
        message = '\n\n'.join(doc_.to_str() for doc_ in docs)
        self.messenger.send_message(message, use_markdown=True)

    def _update_status(self) -> None:
        with self._lock_for_status:
            if self._message_id_for_status and self.messenger.last_message_id != self._message_id_for_status:
                self._message_id_for_status = None

            if not self._message_id_for_status:
                if (
                    self.messenger.last_sent_at
                    and get_current_time() - self.messenger.last_sent_at > datetime.timedelta(minutes=5)
                    and not is_sleep_hours()

                ):
                    logging.info('Send status after 5 min.')
                    self._send_status()

                return

            logging.info('Update status')
            self._send_status()

    def _pipe_for_collecting_stats(self, receivers: typing.Sequence, kwargs: dict) -> typing.Iterator:
        with ProgressBar(self.messenger, title='Collecting stats\\.\\.\\.') as progress_bar:
            count = len(receivers)
            plots = []
            exceptions = []

            for i in range(count):
                try:
                    result = yield
                except Shutdown:
                    raise
                except Exception as e:
                    exceptions.append(e)
                    continue

                if result is not None:
                    if isinstance(result, (tuple, list,)):
                        plots.extend(result)
                    else:
                        plots.append(result)

                progress_bar.set((i + 1) / count)

            for exception in exceptions:
                logging.exception(exception)
                self.messenger.exception(exception)

            if plots:
                self.messenger.send_images(images=plots)
            else:
                self.messenger.send_message('There is still little data')

        yield None

    @interface.command(constants.BotCommands.STATUS)
    def _send_status(self) -> None:
        report = ShortTextReport(state=self.state)
        message = report.generate()

        with self._lock_for_status:
            if self._message_id_for_status:
                message += f'\nUpdated at: `{escape_markdown(report.now.strftime("%d.%m.%Y, %H:%M:%S"))}`'

            self._message_id_for_status = self.messenger.send_message(
                message,
                message_id=self._message_id_for_status,
                use_markdown=True,
            )

    @interface.command(constants.BotCommands.REPORT)
    def _send_report(self) -> None:
        now = datetime.datetime.now()
        hour = now.hour

        if hour < 12:
            greeting = f'{emojize(":sunrise:")} ️*Good morning\\!*'
        elif 12 <= hour <= 17:
            greeting = f'{emojize(":sunset:")} ️*Good afternoon\\!*'
        elif 17 <= hour <= 24:
            greeting = f'{emojize(":night_with_stars:")} ️*Good evening\\!*'
        else:
            greeting = ''

        weather_data = get_weather()
        weather = f'{emojize(":thermometer:")} ️The weather in {weather_data["name"]}: *{weather_data["main"]["temp"]}℃*'
        weather += (
            f' ({weather_data["main"]["temp_min"]} \\.\\. {weather_data["main"]["temp_max"]}), '
            if weather_data["main"]["temp_min"] != weather_data["main"]["temp_max"] else ', '
        )
        weather += f'{weather_data["weather"][0]["description"]}.'

        self.messenger.send_message(f'{greeting}\n\n{weather}', use_markdown=True)

    @interface.command(constants.BotCommands.DB_STATS)
    def _send_db_stats(self) -> None:
        sql = """
        SELECT table_name, pg_size_pretty(pg_relation_size(quote_ident(table_name))) AS table_size
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_size;
        """

        with db.db_engine.connect() as connection:
            db_result = connection.execute(text(sql))

        result = tuple(dict(zip(db_result.keys(), row)) for row in db_result)

        prepared_result = '**Table:**\n'

        for row in result:
            prepared_result += f'`{escape_markdown(row["table_name"])}`: {row["table_size"]}\n'

        prepared_result += '\n**Table Signal:**\n'

        signal_table_stats = Signal.get_table_stats()

        for name, count in signal_table_stats.items():
            prepared_result += f'`{name}`: {count}\n'

        self.messenger.send_message(prepared_result, use_markdown=True)
