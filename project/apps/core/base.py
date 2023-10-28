import abc
import logging
import threading
import typing
from dataclasses import dataclass, field

from libs.messengers.base import BaseMessenger
from libs.task_queue import BaseTaskQueue
from libs.task_queue.dto import RepeatableTask, ScheduledTask
from libs.zigbee.base import ZigBee
from . import events, constants
from ..common import doc
from ..common.base import BaseReceiver
from ..common.state import State
from ..common.types import FrozenDict


@dataclass
class ModuleContext:
    messenger: BaseMessenger
    state: State
    task_queue: BaseTaskQueue
    zig_bee: ZigBee


class BaseModule(abc.ABC):
    doc: doc.Doc
    initial_state: dict = {}
    context: ModuleContext
    messenger: BaseMessenger
    state: State
    task_queue: BaseTaskQueue
    _subscribers_to_events: tuple[BaseReceiver, ...]
    _repeatable_tasks: tuple[RepeatableTask, ...]
    _lock: threading.RLock

    def __init__(self, *, context: ModuleContext) -> None:
        self._lock = threading.RLock()
        self.context = context
        self.messenger = self.context.messenger
        self.state = self.context.state
        self.task_queue = self.context.task_queue

        self.state.create_many(**self.initial_state)
        self._subscribers_to_events = self.subscribe_to_events()
        self._repeatable_tasks = self.init_repeatable_tasks()

        for repeatable_task in self._repeatable_tasks:
            self.task_queue.put_task(repeatable_task)

    def init_repeatable_tasks(self) -> tuple[ScheduledTask, ...]:
        return ()

    def subscribe_to_events(self) -> tuple[BaseReceiver, ...]:
        subscribers: tuple[BaseReceiver, ...] = (
            events.shutdown.connect(self.disable),
        )

        if self.__class__.process_command is not BaseModule.process_command:
            # Process input commands if it's overwritten.
            subscribers += (events.input_command.connect(self.process_command),)

        if hasattr(self, 'doc'):
            subscribers += (events.getting_doc.connect(lambda: self.doc),)

        return subscribers

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
        events.input_command.send(command=Command(name=name, args=args, kwargs=kwargs))


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

    @classmethod
    def from_string(cls, string: str) -> 'Command':
        if string in constants.BOT_COMMAND_ALIASES:
            string = constants.BOT_COMMAND_ALIASES[string]

        params = string.split(' ')
        command_name = params[0]
        command_params = tuple(param.strip() for param in params[1:] if param)
        command_args = []
        command_kwargs = {}

        for i, command_param in enumerate(command_params):
            if '=' in command_param:
                name, value = command_param.split('=', 1)
                command_kwargs[name] = value
            else:
                command_args.append(command_param)

        return Command(
            name=command_name,
            args=command_args,
            kwargs=command_kwargs,
        )


@dataclass
class Message:
    chat_id: typing.Optional[int] = None
    username: typing.Optional[str] = None
    text: typing.Optional[str] = None
    command: typing.Optional[Command] = None
