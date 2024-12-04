import typing

from libs import task_queue

from ...common.events import Receiver
from ..base import ModuleContext
from .base import BaseSignalHandler
from .cpu_temp import CpuTempHandler
from .free_disk_space import FreeDiskSpaceHandler
from .motion_sensor import MotionSensorHandler
from .ram_usage import RamUsageHandler
from .router import RouterHandler
from .temp_hum_sensor import TemperatureHumiditySensorHandler
from .water_leak_sensor import WaterLeakSensorHandler
from .weather import WeatherHandler


class SupremeSignalHandler:
    handlers: tuple[type[BaseSignalHandler], ...] = (
        CpuTempHandler,
        WeatherHandler,
        RamUsageHandler,
        FreeDiskSpaceHandler,
        RouterHandler,
        WaterLeakSensorHandler,
        TemperatureHumiditySensorHandler,
        MotionSensorHandler,
    )
    _inited_handlers: tuple[BaseSignalHandler, ...]

    def __init__(self, *, context: ModuleContext) -> None:
        self._inited_handlers = tuple(handler(context=context) for handler in self.handlers)

    @property
    def count_of_handlers(self) -> int:
        return len(self.handlers)

    def get_tasks(self) -> tuple[task_queue.Task, ...]:
        tasks: list[task_queue.Task] = []

        for handler in self._inited_handlers:
            tasks.extend(handler.get_tasks())

        return tuple(tasks)

    def get_initial_state(self) -> dict[str, typing.Any]:
        initial_state = {}

        for handler in self._inited_handlers:
            initial_state.update(handler.get_initial_state())

        return initial_state

    def get_signals(self) -> tuple[Receiver, ...]:
        signals: list[Receiver] = []

        for handler in self._inited_handlers:
            signals.extend(handler.get_signals())

        return tuple(signals)

    def compress(self) -> typing.Generator:
        for i, handler in enumerate(self._inited_handlers, 1):
            handler.compress()
            yield i / self.count_of_handlers

    def disable(self) -> None:
        for handler in self._inited_handlers:
            handler.disable()
