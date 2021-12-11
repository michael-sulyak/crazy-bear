import datetime
import io
import logging
import os
import typing

from emoji import emojize

from .. import events
from ..base import BaseModule, Command
from ..constants import (
    ARDUINO_IS_ENABLED, BotCommands, CAMERA_IS_AVAILABLE, RECOMMENDATION_SYSTEM_IS_ENABLED,
    VIDEO_RECORDING_IS_ENABLED,
)
from ... import db
from ...arduino.constants import ArduinoSensorTypes
from ...common.constants import INITED_AT
from ...common.utils import (
    convert_params_to_date_range, create_plot, get_cpu_temp,
    get_weather, synchronized_method,
)
from ...core import constants
from ...core.constants import (
    AUTO_SECURITY_IS_ENABLED, CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA,
    VIDEO_SECURITY,
)
from ...devices.utils import get_connected_devices_to_router
from ...messengers.utils import ProgressBar
from ...signals.models import Signal
from ...task_queue import IntervalTask, RepeatableTask, TaskPriorities
from .... import config


class Report(BaseModule):
    _signals_for_clearing = (
        constants.CPU_TEMPERATURE,
        constants.TASK_QUEUE_DELAY,
        constants.RAM_USAGE,
        constants.WEATHER_TEMPERATURE,
        constants.WEATHER_HUMIDITY,
    )
    _timedelta_for_ping: datetime.timedelta = datetime.timedelta(seconds=30)
    _last_cpu_notification: datetime.datetime
    _stats_flags_map = {
        'a': 'arduino',
        'e': 'extra_data',
        'i': 'inner_stats',
        'r': 'router_usage',
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()
        self._last_cpu_notification = now

        self.task_queue.put_task(RepeatableTask(
            target=self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        ))

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
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_cpu_temp_stats),
            events.request_for_statistics.connect(self._create_task_queue_stats),
            events.request_for_statistics.connect(self._create_ram_stats),
        )

    def _pipe(self, receivers, kwargs):
        with ProgressBar(self.messenger, title='Collecting stats...') as progress_bar:
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

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.STATUS:
            self._send_status()
            return True

        if command.name == BotCommands.STATS:
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
                self._pipe,
                date_range=date_range,
                components={self._stats_flags_map[flag] for flag in flags},
            )

            return True

        if command.name == BotCommands.REPORT:
            self._send_report()
            return True

        if command.name == BotCommands.DB_STATS:
            self._send_db_stats()
            return True

        if command.name == BotCommands.HELP:
            tags_info = '\n'.join(
                f'`-{key}` - {value.replace("_", " ").title()}'
                for key, value in self._stats_flags_map.items()
            )

            self.messenger.send_message(
                '`/devices` *<mac>* *<name>* *<is_defining>*',
            )

            return True

        return False

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
        yes, no, nothing = emojize(":check_mark_button:"), emojize(":multiply:"), emojize(':multiply:')
        humidity = Signal.last_aggregated(ArduinoSensorTypes.HUMIDITY)
        temperature = Signal.last_aggregated(ArduinoSensorTypes.TEMPERATURE)

        if humidity is not None:
            humidity = f'{round(humidity, 2)}%'
        else:
            humidity = nothing

        if temperature is not None:
            temperature = f'{round(temperature, 2)}℃'
        else:
            temperature = nothing

        if self.state[CURRENT_FPS] is None:
            current_fps = nothing
        else:
            current_fps = round(self.state[CURRENT_FPS], 2)

        try:
            cpu_temperature = f'{round(get_cpu_temp(), 2)}℃'
        except RuntimeError:
            cpu_temperature = nothing

        connected_devices = get_connected_devices_to_router()
        connected_devices_str = ', '.join(
            f'`{device.name}`' if device.name else f'`Unknown {device.mac_address}`'
            for device in connected_devices
        )

        message = (
            f'️*Crazy Bear* `v{config.VERSION}`\n\n'

            f'{emojize(":floppy_disk:")} *Devices*\n'
            f'Arduino: {yes if self.state[ARDUINO_IS_ENABLED] else no}\n\n'

            f'{emojize(":camera:")} *Camera*\n'
            f'Has camera: {yes if self.state[CAMERA_IS_AVAILABLE] else no}\n'
            f'Camera is used: {yes if self.state[USE_CAMERA] else no}\n'
            f'Video recording: {yes if self.state[VIDEO_RECORDING_IS_ENABLED] else no}\n'
            f'FPS: `{current_fps}`\n\n'

            f'{emojize(":shield:")} *Security*\n'
            f'Security: {yes if self.state[SECURITY_IS_ENABLED] else no}\n'
            f'Auto security: {yes if self.state[AUTO_SECURITY_IS_ENABLED] else no}\n'
            f'Video security: {yes if self.state[VIDEO_SECURITY] else no}\n'
            f'WiFi: {connected_devices_str if connected_devices_str else nothing}\n\n'

            f'{emojize(":bar_chart:")} *Sensors*\n'
            f'Humidity: `{humidity}`\n'
            f'Temperature: `{temperature}`\n'
            f'CPU Temperature: `{cpu_temperature}`\n\n'

            f'{emojize(":clipboard:")} *Other info*\n'
            f'Recommendation system: {yes if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] else no}\n'
            f'Started at: `{self.state[INITED_AT].strftime("%d.%m.%Y, %H:%M:%S")}`'
        )

        self.messenger.send_message(message)

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
            pass
        else:
            Signal.add(signal_type=constants.CPU_TEMPERATURE, value=cpu_temperature)

            now = datetime.datetime.now()

            if now - self._last_cpu_notification > datetime.timedelta(minutes=30):
                if cpu_temperature > 70:
                    self.messenger.send_message('CPU temperature is very high!')
                    self._last_cpu_notification = now - datetime.timedelta(minutes=28)
                elif cpu_temperature > 60:
                    self.messenger.send_message('CPU temperature is high!')
                    self._last_cpu_notification = now

    @staticmethod
    def _save_ram_usage():
        tot_m, used_m, free_m = map(int, os.popen('free -t -m').readlines()[1].split()[1:4])
        value = round(used_m / tot_m * 100, 2)

        Signal.add(signal_type=constants.RAM_USAGE, value=value)

    def _send_report(self) -> None:
        now = datetime.datetime.now()
        hour = now.hour

        if hour < 12:
            greeting = f'{emojize(":sunrise:")} ️*Good morning!*'
        elif 12 <= hour <= 17:
            greeting = f'{emojize(":sunset:")} ️*Good afternoon!*'
        elif 17 <= hour <= 24:
            greeting = f'{emojize(":night_with_stars:")} ️*Good evening!*'
        else:
            greeting = ''

        weather_data = get_weather()
        weather = f'{emojize(":thermometer:")} ️The weather in {weather_data["name"]}: *{weather_data["main"]["temp"]}℃*'
        weather += (
            f' ({weather_data["main"]["temp_min"]} .. {weather_data["main"]["temp_max"]}), '
            if weather_data["main"]["temp_min"] != weather_data["main"]["temp_max"] else ', '
        )
        weather += f'{weather_data["weather"][0]["description"]}.'

        self.messenger.send_message(
            f'{greeting}\n\n'
            f'{weather}'
        )

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
            prepared_result += f'`{row["table_name"]}`: {row["table_size"]}\n'

        prepared_result += '\n**Table Signal:**\n'

        signal_table_stats = Signal.get_table_stats()

        for name, count in signal_table_stats.items():
            prepared_result += f'`{name}`: {count}\n'

        self.messenger.send_message(prepared_result)
