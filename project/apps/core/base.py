import abc
import queue
import typing
from dataclasses import dataclass, field

import schedule

from . import events
from ..common.state import State
from ..common.threads import ThreadPool
from ..messengers import events as messenger_events
from ..messengers.base import BaseMessenger


@dataclass
class CommandHandlerContext:
    messenger: BaseMessenger
    state: State
    message_queue: queue
    scheduler: schedule.Scheduler
    thread_pool: ThreadPool


class BaseCommandHandler(abc.ABC):
    initial_state = {}
    context: CommandHandlerContext
    messenger: BaseMessenger
    state: State
    thread_pool: ThreadPool

    def __init__(self, *, context: CommandHandlerContext) -> None:
        self.context = context

        self.messenger = self.context.messenger
        self.state = self.context.state
        self.thread_pool = self.context.thread_pool

        events.tick.connect(self.update)
        events.shutdown.connect(self.clear)
        messenger_events.input_command.connect(self.process_command)

        self.state.create_many(**self.initial_state)
        self.init_schedule(self.context.scheduler)

    def init_schedule(self, scheduler: schedule.Scheduler) -> None:
        pass

    def process_command(self, command: 'Command') -> typing.Any:
        pass

    def update(self) -> None:
        pass

    def clear(self) -> None:
        pass

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


@dataclass
class Message:
    text: typing.Optional[str] = None
    command: typing.Optional[Command] = None
