import datetime
import typing
from collections import defaultdict

from .. import constants
from ..base import BaseModule, Command
from ...arduino.constants import ArduinoSensorTypes
from ...common.constants import OFF, ON
from ...common.utils import is_sleep_hours, synchronized_method
from ...core import events
from ..constants import BotCommands
from ...signals.models import Signal
from .... import config


class RecommendationSystem(BaseModule):
    initial_state = {
        constants.RECOMMENDATION_SYSTEM_IS_ENABLED: False,
    }
    _last_sent_at_map: typing.Dict[str, datetime.datetime]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.now() - datetime.timedelta(days=365))

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.new_arduino_data.connect(self._process_new_arduino_logs),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RECOMMENDATION_SYSTEM:
            if command.first_arg == ON:
                if self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED]:
                    self.messenger.send_message('Recommendation system is already on')
                else:
                    self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED] = True
                    self.messenger.send_message('Recommendation system is on')
            elif command.first_arg == OFF:
                if self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED]:
                    self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED] = False
                    self.messenger.send_message('Recommendation system is off')
                else:
                    self.messenger.send_message('Recommendation system is already off')
            else:
                return False

            return True

        return False

    @synchronized_method
    def _process_new_arduino_logs(self, signals: typing.List[Signal]) -> None:
        if not self.state[constants.RECOMMENDATION_SYSTEM_IS_ENABLED]:
            return

        last_signal_data = {}

        for signal in reversed(signals):
            if signal.value is None:
                continue

            if signal.type in last_signal_data:
                if last_signal_data.keys() >= {ArduinoSensorTypes.HUMIDITY, ArduinoSensorTypes.TEMPERATURE}:
                    break

                continue

            last_signal_data[signal.type] = signal.value

        humidity = last_signal_data.get(ArduinoSensorTypes.HUMIDITY)
        temperature = last_signal_data.get(ArduinoSensorTypes.TEMPERATURE)

        if humidity is not None:
            can_send_warning = self._can_send_warning('humidity', datetime.timedelta(hours=2))

            if humidity < config.NORMAL_HUMIDITY_RANGE[0] and can_send_warning:
                self.messenger.send_message(f'There is low humidity in the room ({humidity}%)!')
                self._mark_as_sent('humidity')

            if humidity > config.NORMAL_HUMIDITY_RANGE[1] and can_send_warning:
                self.messenger.send_message(f'There is high humidity in the room ({humidity}%)!')
                self._mark_as_sent('humidity')

        if temperature is not None:
            can_send_warning = self._can_send_warning('temperature', datetime.timedelta(hours=2))

            if temperature < config.NORMAL_TEMPERATURE_RANGE[0] and can_send_warning:
                self.messenger.send_message(f'There is a low temperature in the room ({temperature})!')
                self._mark_as_sent('temperature')

            if temperature > config.NORMAL_TEMPERATURE_RANGE[1] and can_send_warning:
                self.messenger.send_message(
                    f'There is a high temperature in the room ({temperature})!',
                )
                self._mark_as_sent('temperature')

    def _can_send_warning(self, name: str, timedelta_for_sending: datetime.timedelta) -> bool:
        now = datetime.datetime.now()

        if is_sleep_hours(now):
            return False

        if now - self._last_sent_at_map[name] <= timedelta_for_sending:
            return False

        if not self.state[constants.USER_IS_CONNECTED_TO_ROUTER]:
            return False

        return True

    def _mark_as_sent(self, name: str) -> None:
        now = datetime.datetime.now()
        self._last_sent_at_map[name] = now
