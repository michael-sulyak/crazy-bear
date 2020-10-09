import datetime
import typing

import schedule

from ..base import BaseCommandHandler, Command
from ...arduino.constants import ARDUINO_IS_ENABLED
from ...arduino.models import ArduinoLog
from ...common.models import Signal
from ...common.utils import check_user_connection_to_router, get_cpu_temp, send_plot
from ...core import constants
from ...core.constants import (
    AUTO_SECURITY_IS_ENABLED, CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA,
    VIDEO_SECURITY,
)
from ...messengers.constants import BotCommands, INITED_AT
from .... import config


class Other(BaseCommandHandler):
    _empty_value = '-'

    def init_schedule(self, scheduler: schedule.Scheduler) -> None:
        scheduler.every(1).hours.do(lambda: Signal.clear(signal_type=constants.CPU_TEMPERATURE))
        scheduler.every(10).seconds.do(self._process_cpu_temperature)

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.STATUS:
            self._send_status()
            return True

        if command.name == BotCommands.STATS:
            self._send_stats(command)
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
            f'CPU Temperature: `{cpu_temperature}`\n'
            f'User is connected to router: `{"True" if check_user_connection_to_router() else "False"}`\n'
            f'FPS: `{current_fps}`\n\n'
            f'Now: `{datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")}`\n'
            f'Started at: `{self.state[INITED_AT].strftime("%d.%m.%Y, %H:%M:%S")}`'
        )

        self.messenger.send_message(message)

    def _send_stats(self, command: Command) -> None:
        stats = Signal.get_avg(
            signal_type=constants.CPU_TEMPERATURE,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if stats:
            send_plot(messenger=self.messenger, stats=stats, title='CPU temperature', attr='value')

    def _process_cpu_temperature(self):
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
