import datetime
import typing
from collections import defaultdict

from ..base import BaseModule, Command
from ..constants import RECOMMENDATION_SYSTEM_IS_ENABLED
from ...arduino.models import ArduinoLog
from ...common.constants import OFF, ON
from ...common.utils import check_user_connection_to_router, is_sleep_hours, synchronized
from ...core import events
from ...messengers.constants import BotCommands


class RecommendationSystem(BaseModule):
    initial_state = {
        RECOMMENDATION_SYSTEM_IS_ENABLED: False,
    }
    _last_sent_at_map: typing.Dict[str, datetime.datetime]
    _timedelta_for_sending: datetime.timedelta = datetime.timedelta(hours=2)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._last_sent_at_map = defaultdict(lambda: datetime.datetime.now() - self._timedelta_for_sending)

    def connect_to_events(self) -> None:
        super().connect_to_events()

        events.new_arduino_logs.connect(self._process_new_arduino_logs)

    @synchronized
    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.RECOMMENDATION_SYSTEM:
            if command.first_arg == ON:
                if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED]:
                    self.messenger.send_message('Recommendation system is already on')
                else:
                    self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] = True
                    self.messenger.send_message('Recommendation system is on')
            elif command.first_arg == OFF:
                if self.state[RECOMMENDATION_SYSTEM_IS_ENABLED]:
                    self.state[RECOMMENDATION_SYSTEM_IS_ENABLED] = False
                    self.messenger.send_message('Recommendation system is off')
                else:
                    self.messenger.send_message('Recommendation system is already off')
            else:
                return False

            return True

        return False

    @synchronized
    def _process_new_arduino_logs(self, new_arduino_logs: typing.List[ArduinoLog]) -> None:
        if not self.state[RECOMMENDATION_SYSTEM_IS_ENABLED]:
            return

        last_arduino_log = new_arduino_logs[-1]

        if last_arduino_log.humidity is not None and last_arduino_log.humidity < 30 and self._can_send_warning('humidity'):
            self.messenger.send_message(f'There is low humidity in the room ({last_arduino_log.humidity}%)!')
            self._mark_as_sent('humidity')

        if last_arduino_log.humidity is not None and last_arduino_log.humidity > 60 and self._can_send_warning('humidity'):
            self.messenger.send_message(f'There is high humidity in the room ({last_arduino_log.humidity}%)!')
            self._mark_as_sent('humidity')

        if last_arduino_log.temperature is not None and last_arduino_log.temperature < 15 and self._can_send_warning('temperature'):
            self.messenger.send_message(f'There is a low temperature in the room ({last_arduino_log.temperature})!')
            self._mark_as_sent('temperature')

        if last_arduino_log.temperature is not None and last_arduino_log.temperature > 30 and self._can_send_warning('temperature'):
            self.messenger.send_message(f'There is a high temperature in the room ({last_arduino_log.temperature})!')
            self._mark_as_sent('temperature')

    def _can_send_warning(self, name: str) -> bool:
        now = datetime.datetime.now()

        if is_sleep_hours(now):
            return False

        if now - self._last_sent_at_map[name] <= self._timedelta_for_sending:
            return False

        if not check_user_connection_to_router():
            return False

        return True

    def _mark_as_sent(self, name: str) -> None:
        now = datetime.datetime.now()
        self._last_sent_at_map[name] = now
