import datetime
import io
import os
import typing
from collections import defaultdict

import schedule
from sqlalchemy import func as sa_func
from emoji import emojize

from .. import events
from ..base import BaseModule, Command
from ..constants import ARDUINO_IS_ENABLED
from ... import db
from ...arduino.models import ArduinoLog
from ...common.models import Signal
from ...common.utils import check_user_connection_to_router, create_plot, get_cpu_temp, get_weather
from ...core import constants
from ...core.constants import (
    AUTO_SECURITY_IS_ENABLED, CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA,
    VIDEO_SECURITY,
)
from ...messengers.constants import BotCommands, INITED_AT
from .... import config


class Report(BaseModule):
    _empty_value = '-'

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(1).hours.do(
                self.task_queue.push,
                lambda: Signal.clear(signal_type=constants.CPU_TEMPERATURE),
            ),
            scheduler.every(1).hours.do(
                self.task_queue.push,
                lambda: Signal.clear(signal_type=constants.TASK_QUEUE_PUSH),
            ),
            scheduler.every(1).hours.do(
                self.task_queue.push,
                lambda: Signal.clear(signal_type=constants.RAM_USAGE),
            ),
            scheduler.every(10).seconds.do(
                self.task_queue.push,
                self._save_cpu_temperature,
            ),
            scheduler.every(10).minutes.do(
                self.task_queue.push,
                self._save_ram_usage,
            ),
            # scheduler.every(5).seconds.do(
            #     self.task_queue.push,
            #     lambda: Signal.add(signal_type=constants.TASK_QUEUE_SIZE, value=len(self.task_queue)),
            # ),
        )

    def connect_to_events(self) -> None:
        super().connect_to_events()

        events.request_for_statistics.connect(self._create_cpu_temp_stats)
        events.request_for_statistics.connect(self._create_task_queue_size_stats)
        events.request_for_statistics.connect(self._create_ram_stats)

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.STATUS:
            self._send_status()
            return True

        if command.name == BotCommands.STATS:
            results, exceptions = events.request_for_statistics.process(command=command)
            self.messenger.start_typing()

            for exception in exceptions:
                self.messenger.exception(exception)

            plots = []

            for result in results:
                if result is None:
                    continue

                if isinstance(result, (tuple, list,)):
                    plots.extend(result)
                else:
                    plots.append(result)

            if plots:
                self.messenger.send_images(images=plots)
            else:
                self.messenger.send_message('There is still little data')

            return True

        if command.name == BotCommands.REPORT:
            self._send_report()
            return True

        if command.name == BotCommands.DB_STATS:
            self._send_db_stats()
            return True

        return False

    def _send_status(self) -> None:
        humidity = self._empty_value
        temperature = self._empty_value
        arduino_data = ArduinoLog.last_avg()

        if arduino_data:
            if arduino_data.humidity is not None:
                humidity = f'{round(arduino_data.humidity, 2)}%'

            if arduino_data.temperature is not None:
                temperature = f'{round(arduino_data.temperature, 2)}℃'

        if self.state[CURRENT_FPS] is None:
            current_fps = self._empty_value
        else:
            current_fps = round(self.state[CURRENT_FPS], 2)

        try:
            cpu_temperature = f'{round(get_cpu_temp(), 2)}℃'
        except RuntimeError:
            cpu_temperature = self._empty_value

        message = (
            f'️*Crazy Bear* v{config.VERSION}\n\n'
            f'Arduino: `{"On" if self.state[ARDUINO_IS_ENABLED] else "Off"}`\n'
            f'Camera: `{"On" if self.state[USE_CAMERA] else "Off"}`\n\n'
            f'Security: `{"On" if self.state[SECURITY_IS_ENABLED] else "Off"}`\n'
            f'Auto security: `{"On" if self.state[AUTO_SECURITY_IS_ENABLED] else "Off"}`\n'
            f'Video security: `{"On" if self.state[VIDEO_SECURITY] else "Off"}`\n\n'
            f'Humidity: `{humidity}`\n'
            f'Temperature: `{temperature}`\n'
            f'CPU Temperature: `{cpu_temperature}`\n\n'
            f'User is connected to router: `{"True" if check_user_connection_to_router() else "False"}`\n'
            f'Task queue size: `{self.context.task_queue.approximate_size}`\n'
            f'FPS: `{current_fps}`\n\n'
            f'Now: `{datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")}`\n'
            f'Started at: `{self.state[INITED_AT].strftime("%d.%m.%Y, %H:%M:%S")}`'
        )

        self.messenger.send_message(message)

    @staticmethod
    def _create_cpu_temp_stats(command: Command) -> typing.Optional[io.BytesIO]:
        cpu_temp_stats = Signal.get_aggregated(
            signal_type=constants.CPU_TEMPERATURE,
            aggregate_function=sa_func.avg,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not cpu_temp_stats:
            return None

        return create_plot(title='CPU temperature', x_attr='time', y_attr='value', stats=cpu_temp_stats)

    @staticmethod
    def _create_ram_stats(command: Command) -> typing.Optional[io.BytesIO]:
        ram_stats = Signal.get_aggregated(
            signal_type=constants.RAM_USAGE,
            aggregate_function=sa_func.avg,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not ram_stats:
            return None

        return create_plot(title='RAM usage', x_attr='time', y_attr='value', stats=ram_stats)

    def _create_task_queue_size_stats(self, command: Command) -> typing.Optional[io.BytesIO]:
        self.task_queue.save_history()

        task_queue_size_stats = Signal.get_aggregated(
            signal_type=constants.TASK_QUEUE_PUSH,
            aggregate_function=sa_func.sum,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if not task_queue_size_stats:
            return None

        return create_plot(title='Task stats', x_attr='time', y_attr='value', stats=task_queue_size_stats)

    def _save_cpu_temperature(self):
        try:
            cpu_temperature = get_cpu_temp()
        except RuntimeError:
            pass
        else:
            Signal.add(signal_type=constants.CPU_TEMPERATURE, value=cpu_temperature)

            if cpu_temperature > 80:
                self.messenger.send_message('CPU temperature is very high!')
            elif cpu_temperature > 70:
                self.messenger.send_message('CPU temperature is high!')

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
        with db.db_engine.connect() as con:
            result = tuple(dict(row) for row in con.execute('SELECT * FROM dbstat;'))

        agg_result = defaultdict(lambda: 0)

        for item in result:
            agg_result[item['name']] += item['pgsize']

        prepared_result = ''

        for name, pg_size in agg_result.items():
            prepared_result += (
                f'Name: {name}\n'
                f'Size: {round(pg_size / 1024 / 1024, 2)} mb.\n\n'
            )

        self.messenger.send_message(prepared_result, parse_mode=None)
