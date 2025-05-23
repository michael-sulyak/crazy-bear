import datetime
import json
import math
import threading
import typing
from functools import partial
from time import sleep

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.messengers.utils import escape_markdown
from libs.task_queue import ScheduledTask, TaskPriorities
from libs.zigbee.exceptions import ZigBeeTimeoutError
from libs.zigbee.lamps.life_control import LCSmartLamp
from project import config

from ...common import interface
from ...common.constants import OFF, ON
from ...common.utils import get_sunrise_time
from ..base import BaseModule, Command
from ..constants import LAST_CRITICAL_SITUATION_OCCURRED_AT, BotCommands
from . import constants


__all__ = ('LampControllerInBedroom',)


@interface.module(
    title='LampControllerInBedroom',
    description=(
        "The module provides an interface for working with the smart lamp. Also, it's a part of the smart home."
    ),
    commands=(
        interface.Command(constants.BotCommands.LAMP, interface.Choices(ON, OFF)),
        interface.Command(constants.BotCommands.LAMP, 'test'),
        interface.Command(constants.BotCommands.LAMP, 'color', interface.Choices(*LCSmartLamp.colors_map.keys())),
        interface.Command(constants.BotCommands.LAMP, 'brightness', interface.Value('brightness', python_type=int)),
        interface.Command(constants.BotCommands.LAMP, 'color_temp', interface.Value('color_temp', python_type=int)),
        interface.Command(constants.BotCommands.LAMP, 'color_temp', interface.Choices(*LCSmartLamp.color_temps)),
        interface.Command(constants.BotCommands.LAMP, 'increase_brightness'),
        interface.Command(constants.BotCommands.LAMP, 'decrease_brightness'),
        interface.Command(constants.BotCommands.LAMP, 'increase_color_temp'),
        interface.Command(constants.BotCommands.LAMP, 'decrease_color_temp'),
        interface.Command(constants.BotCommands.LAMP, 'sunrise'),
    ),
)
class LampControllerInBedroom(BaseModule):
    smart_lamp: LCSmartLamp
    _lock: threading.RLock
    _last_manual_action: datetime.datetime | None = None
    _last_artificial_sunrise_time: datetime.datetime | None = None
    _default_transition: float = 0.5
    _warning_occurred_at: datetime.datetime | None = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.smart_lamp = self.context.smart_devices_map[config.SmartDeviceNames.MAIN_SMART_LAMP]  # type: ignore
        self._lock = threading.RLock()

        self.task_queue.put(
            self._set_lamp_status,
            run_after=datetime.datetime.now() + datetime.timedelta(seconds=5),
            priority=TaskPriorities.LOW,
        )

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {
            constants.MAIN_LAMP_IS_ON: False,
        }

    def init_repeatable_tasks(self) -> tuple[ScheduledTask, ...]:
        repeatable_tasks: tuple[ScheduledTask, ...] = ()

        if config.ARTIFICIAL_SUNRISE_SCHEDULES:
            repeatable_tasks += tuple(
                ScheduledTask(
                    crontab=sunrise_schedule,
                    target=self._run_artificial_sunrise,
                    priority=TaskPriorities.LOW,
                )
                for sunrise_schedule in config.ARTIFICIAL_SUNRISE_SCHEDULES
            )

        return repeatable_tasks

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self.state.subscribe(
                LAST_CRITICAL_SITUATION_OCCURRED_AT,
                self._process_critical_situation,
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        handlers_map: dict[str, typing.Callable] = {
            ON: lambda: self._turn_on_lamp(brightness=command.second_arg and int(command.second_arg)),
            OFF: self._turn_off_lamp,
            'test': self._test_lamp,
            'color': lambda: self.smart_lamp.set_color_by_name(command.second_arg, transition=self._default_transition),
            'brightness': lambda: self.smart_lamp.set_brightness(
                int(command.second_arg), transition=self._default_transition,
            ),
            'color_temp': lambda: self.smart_lamp.set_color_temp(int(command.second_arg)),
            'increase_brightness': lambda: self.smart_lamp.step_brightness(50, transition=self._default_transition),
            'decrease_brightness': lambda: self.smart_lamp.step_brightness(-50, transition=self._default_transition),
            'increase_color_temp': lambda: self.smart_lamp.step_color_temp(50, transition=self._default_transition),
            'decrease_color_temp': lambda: self.smart_lamp.step_color_temp(-50, transition=self._default_transition),
            'sunrise': self._run_artificial_sunrise,
            'state': self._get_state,
            'warning': self._run_warning,
        }

        if command.name == BotCommands.LAMP:
            with self._lock:
                try:
                    handler = handlers_map.get(command.first_arg)

                    if handler:
                        self._last_manual_action = get_current_time()
                        handler()
                        self.messenger.send_message('Done')
                        return True
                except ZigBeeTimeoutError:
                    self.messenger.send_message("Can't connect")
                else:
                    return False

        return False

    def _turn_on_lamp(self, brightness: int | None = None) -> None:
        if brightness:
            self.smart_lamp.turn_on(
                brightness=brightness,
                transition=self._default_transition,
            )
        else:
            self.smart_lamp.turn_on(
                transition=self._default_transition,
            )

        self.state[constants.MAIN_LAMP_IS_ON] = True

    def _turn_off_lamp(self) -> None:
        self.smart_lamp.turn_off(transition=self._default_transition)
        self.state[constants.MAIN_LAMP_IS_ON] = False

    def _test_lamp(self) -> None:
        self.smart_lamp.test()
        self.state[constants.MAIN_LAMP_IS_ON] = False

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
            if self.smart_lamp.is_on():
                self.smart_lamp.reset()

                self.task_queue.put(
                    partial(self._set_lamp_status),
                    run_after=datetime.datetime.now() + datetime.timedelta(seconds=3),
                    priority=TaskPriorities.LOW,
                )

                return

            self.state[constants.MAIN_LAMP_IS_ON] = self.smart_lamp.is_on()
        except ZigBeeTimeoutError:
            pass

    @synchronized_method
    def _run_artificial_sunrise(self, *, step: int = 1) -> None:
        delay_between_steps = datetime.timedelta(seconds=10)
        sunrise_time = datetime.timedelta(minutes=30)
        total_steps = int(sunrise_time.total_seconds() / delay_between_steps.total_seconds())
        max_brightness = self.smart_lamp.brightness_range[1]
        color_temp = 'warmest'

        def _run_next_step() -> None:
            self.task_queue.put(
                self._run_artificial_sunrise,
                kwargs={'step': step + 1},
                run_after=datetime.datetime.now() + delay_between_steps,
                priority=TaskPriorities.LOW,
            )

        brightness = self._calculate_brightness(step=step, max_brightness=max_brightness, total_steps=total_steps)

        if step == 1:
            if self.smart_lamp.is_on():
                return

            if not self.state[constants.USER_IS_AT_HOME]:
                return

            # Note: The below code contains some commands to try to get needed behaviour from the lamp.

            self.smart_lamp.set_color_temp_startup(color_temp)
            sleep(1)
            self.smart_lamp.turn_on(
                brightness=brightness,
                color_temp=color_temp,
                transition=self._default_transition,
            )
            sleep(2)
            self.smart_lamp.set_color_temp(color_temp)
            self.state[constants.MAIN_LAMP_IS_ON] = True

            self._last_artificial_sunrise_time = get_current_time()
            _run_next_step()
            return

        if not self._can_continue_artificial_sunrise():
            return

        prev_brightness = self._calculate_brightness(
            step=step - 1,
            max_brightness=max_brightness,
            total_steps=total_steps,
        )

        if prev_brightness != brightness:
            self.smart_lamp.set_brightness(brightness, transition=1)

        if step >= total_steps:
            assert self._last_artificial_sunrise_time is not None

            delta_to_wait_sunrise = get_sunrise_time() - get_current_time()
            delta_to_wait_one_hour_after_finishing = (
                self._last_artificial_sunrise_time + sunrise_time + datetime.timedelta(hours=1) - get_current_time()
            )
            diff = max(delta_to_wait_sunrise, delta_to_wait_one_hour_after_finishing, datetime.timedelta())

            self.smart_lamp.set_brightness(max_brightness, transition=1)
            self.smart_lamp.set_color_temp('cool', transition=1)

            self.task_queue.put(
                self._turn_down_lamp_artificial_sunrise,
                run_after=datetime.datetime.now() + diff,
                priority=TaskPriorities.LOW,
            )
        else:
            _run_next_step()

    @staticmethod
    def _calculate_brightness(*, step: int, max_brightness: int, total_steps: int) -> int:
        # Sigmoid parameters
        l = max_brightness  # The maximum brightness the lamp can achieve.
        k = 10 / total_steps  # The steepness of the curve. Adjust k dynamically based on the total steps.
        x_0 = total_steps / 2  # The midpoint of the sigmoid function.

        # Current step converted to the sigmoid function's x-value.
        x = step

        # Sigmoid function for smooth brightness transition.
        brightness = l / (1 + math.exp(-k * (x - x_0)))

        # Ensure the brightness is within the valid range for the lamp.
        return max(0, min(int(brightness), max_brightness))

    @synchronized_method
    def _turn_down_lamp_artificial_sunrise(self) -> None:
        if not self._can_continue_artificial_sunrise():
            return

        self.smart_lamp.turn_off(transition=1)
        self.state[constants.MAIN_LAMP_IS_ON] = False

    @synchronized_method
    def _can_continue_artificial_sunrise(self) -> bool:
        return self._last_artificial_sunrise_time is not None and (
            self._last_manual_action is None or self._last_manual_action < self._last_artificial_sunrise_time
        )

    @synchronized_method
    def _get_state(self) -> None:
        state = json.dumps(self.smart_lamp.get_state(), indent=2)
        self.messenger.send_message(
            f'**State of "{self.smart_lamp.friendly_name}"**:\n```json\n{escape_markdown(state)}\n```',
            use_markdown=True,
        )

    @synchronized_method
    def _process_critical_situation(self, name: str, old_value: datetime.datetime | None,
                                    new_value: datetime.datetime) -> None:
        was_empty = self._warning_occurred_at is None
        self._warning_occurred_at = new_value

        if was_empty:
            self.task_queue.put(
                self._run_warning,
                priority=TaskPriorities.HIGH,
            )

    @synchronized_method
    def _run_warning(self, *, turn_on: bool = True, is_new: bool = True) -> None:
        min_brightness = 50
        max_brightness = self.smart_lamp.brightness_range[1]

        if turn_on:
            if is_new:
                self._turn_on_lamp(brightness=max_brightness)
                self.smart_lamp.set_color(self.smart_lamp.colors_map['red'])
            else:
                self.smart_lamp.set_brightness(max_brightness, transition=1)
        else:
            self.smart_lamp.set_brightness(min_brightness, transition=1)

            if (
                self._warning_occurred_at is None
                or datetime.datetime.now() - self._warning_occurred_at > datetime.timedelta(minutes=30)
            ):
                self._turn_off_lamp()
                self._warning_occurred_at = None
                return

        self._last_manual_action = get_current_time()

        self.task_queue.put(
            self._run_warning,
            kwargs={'turn_on': not turn_on, 'is_new': False},
            run_after=datetime.datetime.now() + datetime.timedelta(seconds=3),
            priority=TaskPriorities.HIGH,
        )
