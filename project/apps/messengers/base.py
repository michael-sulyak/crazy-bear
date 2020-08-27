import abc
import queue
import typing
from dataclasses import dataclass, field

import schedule

from . import mixins
from ..common.state import State
from ..common.threads import ThreadPool


class BaseMessenger(mixins.BaseCVMixin, abc.ABC):
    @abc.abstractmethod
    def send_message(self, text: str, *args, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def send_image(self, photo: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        pass

    @abc.abstractmethod
    def error(self, text: str) -> None:
        pass

    @abc.abstractmethod
    def exception(self, exp: Exception) -> None:
        pass

    @abc.abstractmethod
    def start_typing(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def get_updates(self, *args, **kwargs) -> typing.Iterator:
        pass


class BaseCommandHandler(abc.ABC):
    messenger: BaseMessenger
    state: State
    support_commands: typing.Set
    message_queue: queue
    scheduler: schedule.Scheduler
    thread_pool: ThreadPool

    def __init__(self, *,
                 messenger: BaseMessenger,
                 state: State,
                 message_queue: queue,
                 scheduler: schedule.Scheduler,
                 thread_pool: ThreadPool) -> None:
        self.messenger = messenger
        self.state = state
        self.message_queue = message_queue
        self.scheduler = scheduler
        self.thread_pool = thread_pool

        self.init_state()
        self.init_schedule()

    def init_state(self) -> None:
        pass

    def init_schedule(self) -> None:
        pass

    def process_command(self, command: 'Command') -> None:
        pass

    def update(self) -> None:
        pass

    def clear(self) -> None:
        pass

    def _put_command(self, name: str, *args, **kwargs) -> None:
        self.message_queue.put(Message(command=Command(name=name, args=args, kwargs=kwargs)))


@dataclass
class Command:
    name: str
    args: typing.Tuple = field(default_factory=tuple)
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
