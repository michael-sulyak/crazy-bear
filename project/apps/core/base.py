import abc
import logging
import threading
import typing
from dataclasses import dataclass, field

from . import events
from ..common.events import Receiver
from ..common.state import State
from ..common.types import FrozenDict
from ..messengers import events as messenger_events
from ..messengers.base import BaseMessenger
from ..task_queue import BaseTaskQueue, UniqueTaskQueue
from ..task_queue.dto import RepeatableTask
from ..zigbee.base import ZigBee


@dataclass
class ModuleContext:
    messenger: BaseMessenger
    state: State
    task_queue: BaseTaskQueue
    zig_bee: ZigBee


class BaseModule(abc.ABC):
    initial_state = {}
    context: ModuleContext
    messenger: BaseMessenger
    state: State
    task_queue: BaseTaskQueue
    unique_task_queue: UniqueTaskQueue
    _subscribers_to_events: typing.Tuple[Receiver, ...]
    _repeatable_tasks: typing.Tuple[RepeatableTask, ...]
    _lock: typing.Union[threading.Lock, threading.RLock]

    def __init__(self, *, context: ModuleContext) -> None:
        self._lock = threading.RLock()
        self.context = context
        self.messenger = self.context.messenger
        self.state = self.context.state
        self.task_queue = self.context.task_queue
        self.unique_task_queue = UniqueTaskQueue(task_queue=self.context.task_queue)

        self.state.create_many(**self.initial_state)
        self._subscribers_to_events = self.subscribe_to_events()
        self._repeatable_tasks = self.init_repeatable_tasks()

        for repeatable_task in self._repeatable_tasks:
            self.task_queue.put_task(repeatable_task)

    def init_repeatable_tasks(self) -> tuple:
        return ()

    def subscribe_to_events(self) -> typing.Tuple[Receiver, ...]:
        return (
            events.shutdown.connect(self.disable),
            messenger_events.input_command.connect(self.process_command),
        )

    def process_command(self, command: 'Command') -> typing.Any:
        pass

    def disable(self) -> None:
        logging.info('[shutdown] Disable module "%s"...', self.__class__.__name__)

        for subscriber in self._subscribers_to_events:
            subscriber.disconnect()

        for repeatable_task in self._repeatable_tasks:
            repeatable_task.cancel()

    @staticmethod
    def _run_command(name: str, *args, **kwargs) -> None:
        messenger_events.input_command.send(command=Command(name=name, args=args, kwargs=kwargs))


@dataclass
class Command:
    name: str
    args: typing.Sequence = field(
        default_factory=tuple,
    )
    kwargs: typing.Mapping = field(
        default_factory=FrozenDict,
    )

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(\'{self.name}\', args={self.args}, kwargs={self.kwargs})'

    @property
    def first_arg(self) -> typing.Any:
        return self.get_arg(0)

    @property
    def second_arg(self) -> typing.Any:
        return self.get_arg(1)

    @property
    def third_arg(self) -> typing.Any:
        return self.get_arg(2)

    def get_first_arg(self, default: typing.Any, *, skip_flags: bool = False) -> typing.Any:
        return self.get_arg(0, default, skip_flags=skip_flags)

    def get_second_arg(self, default: typing.Any, *, skip_flags: bool = False) -> typing.Any:
        return self.get_arg(1, default, skip_flags=skip_flags)

    def get_third_arg(self, default: typing.Any, *, skip_flags: bool = False) -> typing.Any:
        return self.get_arg(2, default, skip_flags=skip_flags)

    def get_arg(self, index: int, default: typing.Any = None, *, skip_flags: bool = False) -> typing.Any:
        args = self.args

        if skip_flags:
            args = tuple(arg for arg in self.args if not arg.startswith('-'))

        if len(args) <= index:
            return default

        return args[index]

    def get_flags(self) -> typing.Set[str]:
        return set(arg for arg in self.args if arg.startswith('-'))

    def get_cleaned_flags(self) -> typing.Set[str]:
        return set(arg[1:] for arg in self.get_flags())


@dataclass
class Message:
    chat_id: typing.Optional[int] = None
    username: typing.Optional[str] = None
    text: typing.Optional[str] = None
    command: typing.Optional[Command] = None
