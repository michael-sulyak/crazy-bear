import datetime
import typing
from time import sleep

from . import constants
from ..base import BaseModule, Command
from ..constants import BotCommands
from ...common.constants import OFF, ON
from ...zigbee.lamps.life_control import LCSmartLamp


__all__ = (
    'SmartAlarmClock',
)


class SmartAlarmClock(BaseModule):
    smart_lamp: LCSmartLamp

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.smart_lamp = LCSmartLamp('lamp:main_room', zig_bee=self.context.zig_bee)
        self.task_queue.put(
            lambda: (
                # self.smart_lamp.set_color_temp_startup(500),
                self.state.set(constants.MAIN_LAMP_IS_ON, self.smart_lamp.is_on()),
            ),
            run_after=datetime.datetime.now() + datetime.timedelta(seconds=5),
        )

    @property
    def initial_state(self) -> typing.Dict[str, typing.Any]:
        return {
            constants.MAIN_LAMP_IS_ON: False,
        }

    def init_repeatable_tasks(self) -> tuple:
        hours, minutes = 13, 55

        return (
            # ScheduledTask(
            #     crontab=CronTab(f'{minutes} {hours} * * *'),
            #     target=self._step_1,
            #     priority=TaskPriorities.LOW,
            # ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.LAMP:
            default_transition = 1

            if command.first_arg == ON:
                self.smart_lamp.turn_on(transition=default_transition)
                self.state[constants.MAIN_LAMP_IS_ON] = True
            elif command.first_arg == OFF:
                self.smart_lamp.turn_off(transition=default_transition)
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

            self.messenger.send_message('Done')

            return True

        return False

    def _step_1(self) -> None:
        self.smart_lamp.turn_off()
        sleep(10)

        if self.smart_lamp.is_on():
            return

        self.smart_lamp.set_color_by_name('yellow')
        self.smart_lamp.set_brightness(20)
        self.smart_lamp.turn_on(transition=5)
        self.task_queue.put(
            self._step_2,
            run_after=datetime.datetime.now() + datetime.timedelta(minutes=2),
        )

    def _step_2(self) -> None:
        if self.smart_lamp.is_off():
            return

        self.smart_lamp.set_brightness(50, transition=10)

        self.task_queue.put(
            self._step_3,
            run_after=datetime.datetime.now() + datetime.timedelta(minutes=2),
        )

    def _step_3(self) -> None:
        if self.smart_lamp.is_off():
            return

        self.smart_lamp.set_brightness(100, transition=10)

        self.task_queue.put(
            self._step_4,
            run_after=datetime.datetime.now() + datetime.timedelta(minutes=5),
        )

    def _step_4(self) -> None:
        if self.smart_lamp.is_off():
            return

        self.smart_lamp.set_brightness(200, transition=10)
        self.smart_lamp.set_color((255, 255, 255,), transition=10)
