import datetime
import threading
import typing
from functools import partial

import pytz

from project import config
from . import constants
from ..base import BaseModule, Command
from ..constants import BotCommands
from ...common.constants import OFF, ON
from ...common.utils import current_time, get_weather, synchronized_method
from ...task_queue import ScheduledTask, TaskPriorities
from ...zigbee.exceptions import ZigBeeTimeoutError
from ...zigbee.lamps.life_control import LCSmartLamp


__all__ = (
    'SmartLampController',
)


class SmartLampController(BaseModule):
    smart_lamp: LCSmartLamp
    _lock: threading.RLock
    _last_manual_action: typing.Optional[datetime.datetime] = None
    _last_artificial_sunrise_time: typing.Optional[datetime.datetime] = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.smart_lamp = LCSmartLamp(config.MAIN_SMART_LAMP, zig_bee=self.context.zig_bee)
        self._lock = threading.RLock()

        self.task_queue.put(
            self._set_lamp_status,
            run_after=datetime.datetime.now() + datetime.timedelta(seconds=5),
            priority=TaskPriorities.LOW,
        )

    @property
    def initial_state(self) -> typing.Dict[str, typing.Any]:
        return {
            constants.MAIN_LAMP_IS_ON: False,
        }

    def init_repeatable_tasks(self) -> tuple:
        repeatable_tasks = ()

        if config.ARTIFICIAL_SUNRISE_TIME:
            repeatable_tasks += (
                ScheduledTask(
                    crontab=config.ARTIFICIAL_SUNRISE_TIME,
                    target=self._run_artificial_sunrise,
                    priority=TaskPriorities.LOW,
                ),
            )

        return repeatable_tasks

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.LAMP:
            default_transition = 1

            with self._lock:
                try:
                    if command.first_arg == ON:
                        self.smart_lamp.turn_on(transition=default_transition)
                        self.state[constants.MAIN_LAMP_IS_ON] = True
                    elif command.first_arg == OFF:
                        self.smart_lamp.turn_off(transition=default_transition)
                        self.state[constants.MAIN_LAMP_IS_ON] = False
                    elif command.first_arg == 'test':
                        self.smart_lamp.test()
                        self.state[constants.MAIN_LAMP_IS_ON] = False
                    elif command.first_arg == 'color':
                        self.smart_lamp.set_color_by_name(command.second_arg, transition=default_transition)
                    elif command.first_arg == 'brightness':
                        self.smart_lamp.set_brightness(int(command.second_arg), transition=default_transition)
                    elif command.first_arg == 'color_temp':
                        self.smart_lamp.set_color_temp(int(command.second_arg), transition=default_transition)
                    elif command.first_arg == 'increase_brightness':
                        self.smart_lamp.step_brightness(50, transition=default_transition)
                    elif command.first_arg == 'decrease_brightness':
                        self.smart_lamp.step_brightness(-50, transition=default_transition)
                    elif command.first_arg == 'increase_color_temp':
                        self.smart_lamp.step_color_temp(50, transition=default_transition)
                    elif command.first_arg == 'decrease_color_temp':
                        self.smart_lamp.step_color_temp(-50, transition=default_transition)
                    else:
                        return False
                except ZigBeeTimeoutError:
                    self.messenger.send_message('Can\'t connect')

                self._last_manual_action = datetime.datetime.now()
                self.messenger.send_message('Done')

            return True

        return False

    def _set_lamp_status(self, attempt: int = 1) -> None:
        if not self.context.zig_bee.is_health():
            if attempt <= 3:
                self.task_queue.put(
                    partial(self._set_lamp_status, attempt=attempt + 1),
                    run_after=datetime.datetime.now() + datetime.timedelta(seconds=10),
                    priority=TaskPriorities.LOW,
                )

            return

        try:
            self.state[constants.MAIN_LAMP_IS_ON] = self.smart_lamp.is_on()
        except ZigBeeTimeoutError:
            pass

    @synchronized_method
    def _run_artificial_sunrise(self, *, step: int = 1) -> None:
        def _run_next_step(timedelta: datetime.timedelta) -> None:
            self.task_queue.put(
                self._run_artificial_sunrise,
                kwargs={'step': step + 1},
                run_after=datetime.datetime.now() + timedelta,
            )

        if step == 1:
            if self.smart_lamp.is_on():
                return

            if not self.state[constants.USER_IS_CONNECTED_TO_ROUTER]:
                return

            if (current_time() - self._get_real_sunrise_time()) > datetime.timedelta(minutes=20):
                return

            self.smart_lamp.turn_on(
                brightness=20,
                transition=1,
            )

            self._last_artificial_sunrise_time = datetime.datetime.now()
            _run_next_step(datetime.timedelta(minutes=1))
            return

        if not self._can_continue_artificial_sunrise:
            return

        brightness = step * 20

        if brightness > self.smart_lamp.MAX_BRIGHTNESS:
            brightness = self.smart_lamp.MAX_BRIGHTNESS

        self.smart_lamp.set_brightness(brightness)

        if brightness == self.smart_lamp.MAX_BRIGHTNESS:
            diff = self._get_real_sunrise_time() - current_time()
            diff += datetime.timedelta(minutes=20)

            if diff < datetime.timedelta(minutes=30):
                diff = datetime.timedelta(minutes=30)

            self.task_queue.put(
                self._turn_down_lamp,
                run_after=datetime.datetime.now() + diff,
            )
        else:
            _run_next_step(datetime.timedelta(minutes=1))

    @synchronized_method
    def _turn_down_lamp(self) -> None:
        if not self._can_continue_artificial_sunrise:
            return

        self.smart_lamp.turn_off(transition=1)

    @synchronized_method
    def _can_continue_artificial_sunrise(self) -> None:
        return self._last_artificial_sunrise_time and (
                self._last_manual_action is None
                or self._last_manual_action < self._last_artificial_sunrise_time
        )

    @staticmethod
    def _get_real_sunrise_time() -> datetime.datetime:
        weather_info = get_weather()
        sunrise_dt = datetime.datetime.fromtimestamp(weather_info['sys']['sunrise'])
        sunrise_dt -= datetime.timedelta(seconds=weather_info['timezone'])
        return pytz.UTC.localize(sunrise_dt)