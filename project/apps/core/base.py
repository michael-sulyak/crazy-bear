import abc
import queue
import threading
import typing
from dataclasses import dataclass, field

import schedule

from . import events
from ..common.events import Receiver
from ..common.state import State
from ..task_queue import BaseTaskQueue, UniqueTaskQueue
from ..messengers import events as messenger_events
from ..messengers.base import BaseMessenger


@dataclass
class ModuleContext:
    messenger: BaseMessenger
    state: State
    scheduler: schedule.Scheduler
    task_queue: BaseTaskQueue


class BaseModule(abc.ABC):
    initial_state = {}
    context: ModuleContext
    messenger: BaseMessenger
    state: State
    task_queue: BaseTaskQueue
    unique_task_queue: UniqueTaskQueue
    _schedule_jobs: tuple
    _subscribers_to_events: typing.Tuple[Receiver, ...]
    _lock: typing.Union[threading.Lock, threading.RLock]

    def __init__(self, *, context: ModuleContext) -> None:
        self._lock = threading.RLock()
        self.context = context
        self.messenger = self.context.messenger
        self.state = self.context.state
        self.task_queue = self.context.task_queue
        self.unique_task_queue = UniqueTaskQueue(task_queue=self.context.task_queue)

        self.state.create_many(**self.initial_state)
        self._schedule_jobs = self.init_schedule(self.context.scheduler)
        self._subscribers_to_events = self.subscribe_to_events()

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return ()

    def subscribe_to_events(self) -> typing.Tuple[Receiver, ...]:
        return (
            events.shutdown.connect(self.disable),
            messenger_events.input_command.connect(self.process_command),
        )

    def process_command(self, command: 'Command') -> typing.Any:
        pass

    def disable(self) -> None:
        for job in self._schedule_jobs:
            self.context.scheduler.cancel_job(job)

        for subscriber in self._subscribers_to_events:
            subscriber.disconnect()

    @staticmethod
    def _run_command(name: str, *args, **kwargs) -> None:
        messenger_events.input_command.send(command=Command(name=name, args=args, kwargs=kwargs))


@dataclass
class Command:
    name: str
    args: typing.Union[typing.Tuple, typing.List] = field(default_factory=tuple)
    kwargs: typing.Dict = field(default_factory=dict)

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
    text: typing.Optional[str] = None
    command: typing.Optional[Command] = None
