import abc
import queue
import threading
import typing
from dataclasses import dataclass, field

import schedule

from . import events
from ..common.events import Receiver
from ..common.state import State
from ..common.threads import TaskQueue, UniqueTaskQueue
from ..messengers import events as messenger_events
from ..messengers.base import BaseMessenger


@dataclass
class CommandHandlerContext:
    messenger: BaseMessenger
    state: State
    message_queue: queue
    scheduler: schedule.Scheduler
    task_queue: TaskQueue


class BaseModule(abc.ABC):
    initial_state = {}
    context: CommandHandlerContext
    messenger: BaseMessenger
    state: State
    task_queue: TaskQueue
    unique_task_queue: UniqueTaskQueue
    _schedule_jobs: tuple
    _subscribers_to_events: typing.Tuple[Receiver, ...]
    _lock: typing.Union[threading.Lock, threading.RLock]

    def __init__(self, *, context: CommandHandlerContext) -> None:
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
            events.tick.connect(self.tick),
            events.shutdown.connect(self.disable),
            messenger_events.input_command.connect(self.process_command),
        )

    def process_command(self, command: 'Command') -> typing.Any:
        pass

    def tick(self) -> None:
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

    def get_first_arg(self, default: typing.Any) -> typing.Any:
        return self.get_arg(0, default)

    def get_second_arg(self, default: typing.Any) -> typing.Any:
        return self.get_arg(1, default)

    def get_third_arg(self, default: typing.Any) -> typing.Any:
        return self.get_arg(2, default)

    def get_arg(self, index: int, default: typing.Any = None) -> typing.Any:
        if len(self.args) <= index:
            return default

        return self.args[index]

    def is_same(self, name, *args, **kwargs) -> bool:
        return self.name == name and self.args == args and self.kwargs == kwargs


@dataclass
class Message:
    text: typing.Optional[str] = None
    command: typing.Optional[Command] = None
