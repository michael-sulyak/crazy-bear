import typing

from .arduino import ArduinoHandler
from .base import BaseAdvancedSignalHandler
from .cpu_temp import CpuTempHandler
from .free_disk_space import FreeDiskSpaceHandler
from .ram_usage import RamUsageHandler
from .weather import WeatherHandler
from ... import task_queue
from ...common.events import Receiver
from ...common.state import State
from ...messengers.base import BaseMessenger


class SupremeSignalHandler:
    handlers: tuple[typing.Type[BaseAdvancedSignalHandler], ...] = (
        CpuTempHandler,
        WeatherHandler,
        RamUsageHandler,
        FreeDiskSpaceHandler,
        ArduinoHandler,
    )
    _inited_handlers: tuple[BaseAdvancedSignalHandler, ...]

    def __init__(self, *, messenger: BaseMessenger, state: State) -> None:
        self._inited_handlers = tuple(
            handler(messenger=messenger, state=state)
            for handler in self.handlers
        )

    @property
    def count_of_handlers(self) -> int:
        return len(self.handlers)

    def get_tasks(self) -> tuple[task_queue.Task, ...]:
        tasks = []

        for handler in self._inited_handlers:
            tasks.extend(handler.get_tasks())

        return tuple(tasks)

    def get_signals(self) -> tuple[Receiver, ...]:
        signals = []

        for handler in self._inited_handlers:
            signals.extend(handler.get_signals())

        return tuple(signals)

    def compress(self) -> typing.Generator:
        for i, handler in enumerate(self._inited_handlers, 1):
            handler.compress()
            yield i / self.count_of_handlers
