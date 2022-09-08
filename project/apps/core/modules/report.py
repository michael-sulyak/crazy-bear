import datetime
import io
import logging
import threading
import typing

from emoji import emojize

from .. import events
from ..base import BaseModule, Command
from ..utils.reports import ShortTextReport
from ... import db
from ...common import doc
from ...common.utils import (
    convert_params_to_date_range, create_plot, get_cpu_temp,
    get_ram_usage, get_weather, synchronized_method, get_free_disk_space, current_time,
)
from ...core import constants
from ...messengers.utils import ProgressBar, escape_markdown
from ...signals.models import Signal
from ...task_queue import IntervalTask, TaskPriorities


class Report(BaseModule):
    doc = doc.generate_doc(
        title='Report',
        commands=(
            doc.CommandDef(constants.BotCommands.STATUS),
            doc.CommandDef(constants.BotCommands.REPORT),
            doc.CommandDef(constants.BotCommands.HELP),
            doc.CommandDef(constants.BotCommands.DB_STATS),
            doc.CommandDef(
                constants.BotCommands.STATS,
                doc.VarDef('number', type='int'),
                doc.OptionsDef('days', 'hours', 'minutes', 'seconds'),
                flags=(doc.FlagDef('f'), doc.FlagDef('s'), doc.FlagDef('e'), doc.FlagDef('a'), doc.FlagDef('r'),),
            ),
        ),
    )

    _signals_for_clearing = (
        constants.CPU_TEMPERATURE,
        constants.TASK_QUEUE_DELAY,
        constants.RAM_USAGE,
        constants.WEATHER_TEMPERATURE,
        constants.WEATHER_HUMIDITY,
    )
    _timedelta_for_ping: datetime.timedelta = datetime.timedelta(seconds=30)
    _last_cpu_notification: datetime.datetime
    _last_ram_notification: datetime.datetime
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

        now = datetime.datetime.now()
        self._last_cpu_notification = now
        self._last_ram_notification = now
        self._last_disk_space_notification = now
        self._lock_for_status = threading.RLock()

        self.task_queue.put(
            self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        )

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._save_cpu_temperature,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(seconds=10),
            ),
            IntervalTask(
                target=self._save_weather_data,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=5),
            ),
            IntervalTask(
                target=self._save_ram_usage,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=10),
            ),
            IntervalTask(
                target=self._save_free_disk_space,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=10),
            ),
            IntervalTask(
                target=self._update_status,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=1),
            ),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_cpu_temp_stats),
            events.request_for_statistics.connect(self._create_task_queue_stats),
            events.request_for_statistics.connect(self._create_ram_stats),
            events.request_for_statistics.connect(self._create_free_disk_space_stats),
        )

    def process_command(self, command: Command) -> typing.Any:
        with self._lock_for_status:
            self._message_id_for_status = None

        if command.name == constants.BotCommands.STATUS:
            self._send_status()
            return True

        if command.name == constants.BotCommands.STATS:
            delta_type: str = command.get_second_arg('hours', skip_flags=True)
            delta_value: str = command.get_first_arg('24', skip_flags=True)

            if delta_type not in ('days', 'hours', 'minutes', 'seconds',):
                self.messenger.send_message('Wrong a delta type')
                return True

            if delta_value.isdigit():
                delta_value: int = int(delta_value)
            else:
                self.messenger.send_message('Wrong a delta value')
                return True

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

            return True

        if command.name == constants.BotCommands.REPORT:
            self._send_report()
            return True

        if command.name == constants.BotCommands.DB_STATS:
            self._send_db_stats()
            return True

        if command.name == constants.BotCommands.HELP:
            self.messenger.send_message('\n\n'.join(events.getting_doc.process()[0]), use_markdown=True)
            return True

        return False

    def _update_status(self) -> None:
        with self._lock_for_status:
            if self._message_id_for_status and self.messenger.last_message_id != self._message_id_for_status:
                self._message_id_for_status = None

            if not self._message_id_for_status:
                if (
                        self.messenger.last_sent_at
                        and current_time() - self.messenger.last_sent_at > datetime.timedelta(minutes=5)
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

    @synchronized_method
    def _ping_task_queue(self, *, sent_at: datetime.datetime) -> None:
        now = datetime.datetime.now()
        diff = datetime.datetime.now() - sent_at - self._timedelta_for_ping
        Signal.add(signal_type=constants.TASK_QUEUE_DELAY, value=diff.total_seconds(), received_at=now)

        now = datetime.datetime.now()

        self.task_queue.put(
            self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        )

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

    @staticmethod
    def _create_cpu_temp_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                               components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        cpu_temp_stats = Signal.get_aggregated(
            signal_type=constants.CPU_TEMPERATURE,
            datetime_range=date_range,
        )

        if not cpu_temp_stats:
            return None

        return create_plot(title='CPU temperature', x_attr='aggregated_time', y_attr='value', stats=cpu_temp_stats)

    @staticmethod
    def _create_ram_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                          components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        ram_stats = Signal.get_aggregated(
            signal_type=constants.RAM_USAGE,
            datetime_range=date_range,
        )

        if not ram_stats:
            return None

        return create_plot(title='RAM usage (%)', x_attr='aggregated_time', y_attr='value', stats=ram_stats)

    @staticmethod
    def _create_free_disk_space_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                                      components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        free_disk_space_stats = Signal.get_aggregated(
            signal_type=constants.FREE_DISK_SPACE,
            datetime_range=date_range,
        )

        if not free_disk_space_stats:
            return None

        return create_plot(
            title='Free disk space (MB)',
            x_attr='aggregated_time',
            y_attr='value',
            stats=free_disk_space_stats,
        )

    @staticmethod
    def _create_task_queue_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                                 components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        task_queue_size_stats = Signal.get(
            signal_type=constants.TASK_QUEUE_DELAY,
            datetime_range=date_range,
        )

        if not task_queue_size_stats:
            return None

        return create_plot(
            title='Task queue delay stats (sec.)',
            x_attr='received_at',
            y_attr='value',
            stats=task_queue_size_stats,
        )

    @synchronized_method
    def _save_weather_data(self) -> None:
        weather = get_weather()
        Signal.add(signal_type=constants.WEATHER_TEMPERATURE, value=weather['main']['temp'])
        Signal.add(signal_type=constants.WEATHER_HUMIDITY, value=weather['main']['humidity'])

    @synchronized_method
    def _save_cpu_temperature(self) -> None:
        try:
            cpu_temperature = get_cpu_temp()
        except RuntimeError:
            return

        Signal.add(signal_type=constants.CPU_TEMPERATURE, value=cpu_temperature)

        now = datetime.datetime.now()
        diff = now - self._last_cpu_notification

        if cpu_temperature > 90 and diff > datetime.timedelta(minutes=5):
            self.messenger.send_message('CPU temperature is very high!')
        elif cpu_temperature > 70 and diff > datetime.timedelta(minutes=20):
            self.messenger.send_message('CPU temperature is very high!')
        elif cpu_temperature > 60 and diff > datetime.timedelta(minutes=60):
            self.messenger.send_message('CPU temperature is high!')

        self._last_cpu_notification = now

    def _save_ram_usage(self) -> None:
        ram_usage = round(get_ram_usage() * 100, 2)
        Signal.add(signal_type=constants.RAM_USAGE, value=ram_usage)

        now = datetime.datetime.now()
        diff = now - self._last_ram_notification

        if ram_usage > 90 and diff > datetime.timedelta(hours=1):
            self.messenger.send_message('Running out of RAM!!!')
        elif ram_usage > 80 and diff > datetime.timedelta(hours=2):
            self.messenger.send_message('Running out of RAM!!!')
        elif ram_usage > 60 and diff > datetime.timedelta(hours=3):
            self.messenger.send_message('Running out of RAM!')

        self._last_ram_notification = now

    def _save_free_disk_space(self) -> None:
        disk_space_usage = get_free_disk_space()
        Signal.add(signal_type=constants.FREE_DISK_SPACE, value=disk_space_usage)

        now = datetime.datetime.now()
        diff = now - self._last_disk_space_notification

        if disk_space_usage < 100 * 1024 and diff > datetime.timedelta(hours=1):
            self.messenger.send_message('Running out of the disk space!!!')
        elif disk_space_usage < 200 * 1024 and diff > datetime.timedelta(hours=2):
            self.messenger.send_message('Running out of the disk space!!!')
        elif disk_space_usage < 500 * 1024 and diff > datetime.timedelta(hours=3):
            self.messenger.send_message('Running out of the disk space!')

        self._last_disk_space_notification = now

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

    def _send_db_stats(self) -> None:
        sql = """
        SELECT table_name, pg_size_pretty(pg_relation_size(quote_ident(table_name))) AS table_size
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_size;
        """
        with db.db_engine.connect() as con:
            result = tuple(dict(row) for row in con.execute(sql))

        prepared_result = '**Table:**\n'

        for row in result:
            prepared_result += f'`{escape_markdown(row["table_name"])}`: {row["table_size"]}\n'

        prepared_result += '\n**Table Signal:**\n'

        signal_table_stats = Signal.get_table_stats()

        for name, count in signal_table_stats.items():
            prepared_result += f'`{name}`: {count}\n'

        self.messenger.send_message(prepared_result, use_markdown=True)
