import datetime

from emoji import emojize

from project import config
from .. import constants
from ...arduino.base import ArduinoConnector
from ...arduino.constants import ARDUINO_CONNECTOR
from ...arduino.models import ArduinoLog
from ...common.models import Signal
from ...common.utils import get_cpu_temp, send_plot
from ...guard.constants import CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA, VIDEO_GUARD
from ...messengers.base import BaseBotCommandHandler, MessengerCommand
from ...messengers.constants import INITED_AT


class Other(BaseBotCommandHandler):
    support_commands = {
        constants.BotCommands.INIT,
        constants.BotCommands.GOOD_NIGHT,
        constants.BotCommands.STATUS,
        constants.BotCommands.STATS,
    }
    _last_clear_at: datetime
    _last_processed_at: datetime
    _empty_value = '-'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()
        self._last_clear_at = now
        self._last_processed_at = now

    def update(self) -> None:
        now = datetime.datetime.now()

        if now - self._last_processed_at >= datetime.timedelta(seconds=5):
            self._last_processed_at = now

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

            if now - self._last_clear_at >= datetime.timedelta(hours=1):
                Signal.clear(signal_type=constants.CPU_TEMPERATURE)
                self._last_clear_at = now

    def process_command(self, command: MessengerCommand) -> None:
        if command.name == constants.BotCommands.INIT:
            self.messenger.send_message('Hello!')
        elif command.name == constants.BotCommands.GOOD_NIGHT:
            self.process_command(MessengerCommand(name=constants.BotCommands.REPORT))
            message = f'{emojize(":volcano:")} ️What you useful did today?'
            self.messenger.send_message(message)
        elif command.name == constants.BotCommands.STATUS:
            arduino_connector: ArduinoConnector = self.state[ARDUINO_CONNECTOR]
            arduino_data = None
            humidity = self._empty_value
            temperature = self._empty_value

            if arduino_connector:
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
                f'Arduino: `{"On" if arduino_connector and arduino_connector.is_active else "Off"}`\n'
                f'Camera: `{"On" if self.state[USE_CAMERA] else "Off"}`\n\n'
                f'Security: `{"On" if self.state[SECURITY_IS_ENABLED] else "Off"}`\n'
                f'Video guard: `{"On" if self.state[VIDEO_GUARD] else "Off"}`\n\n'
                f'Humidity: `{humidity}`\n'
                f'Temperature: `{temperature}`\n'
                f'CPU Temperature: `{cpu_temperature}`\n'
                f'FPS: `{current_fps}`\n\n'
                f'Now: `{datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")}`\n'
                f'Started at: `{self.state[INITED_AT].strftime("%d.%m.%Y, %H:%M:%S")}`'
            )

            self.messenger.send_message(message)
        elif command.name == constants.BotCommands.STATS:
            self._show_stats(command)

    def _show_stats(self, command: MessengerCommand) -> None:
        stats = Signal.get_avg(
            signal_type=constants.CPU_TEMPERATURE,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if stats:
            send_plot(messenger=self.messenger, stats=stats, title='CPU temperature', attr='value')
