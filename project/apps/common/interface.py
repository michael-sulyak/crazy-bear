import abc
import dataclasses
import inspect
import typing
from collections import defaultdict
from functools import cached_property

from libs.messengers.utils import escape_markdown


if typing.TYPE_CHECKING:
    from project.apps.core.base import Command as OuterCommand


@dataclasses.dataclass
class Module:
    title: str
    use_auto_mapping_for_commands: bool
    description: typing.Optional[str] = None
    commands: tuple['Command', ...] = ()
    commands_map: dict[str, list['Command']] = dataclasses.field(
        default_factory=lambda: defaultdict(list),
    )

    def __post_init__(self) -> None:
        for command_ in self.commands:
            self.commands_map[command_.name].append(command_)

    def to_str(self) -> str:
        result = f'*{escape_markdown(self.title)}*'

        if self.description:
            result += f'\n_{escape_markdown(self.description)}_'

        if self.commands:
            str_commands = '\n'.join(command.to_str() for command in self.commands)
            result += f'\n\n{str_commands}'

        return result


class Command:
    name: str
    params: tuple[typing.Union['BaseParam', str], ...]
    flags: tuple['Flag', ...]
    method_name: str | None

    def __init__(
        self,
        name: str,
        *params: typing.Union['BaseParam', str],
        flags: tuple['Flag', ...] = (),
        method_name: str | None = None,
    ) -> None:
        self.name = name
        self.params = params
        self.flags = flags
        self.method_name = method_name

    def can_handle(self, outer_command: 'OuterCommand') -> bool:
        if self.name != outer_command.name:
            return False

        cleaned_args = outer_command.get_cleaned_args()

        if len(self.params) > len(cleaned_args):
            return False

        for i, param in enumerate(self.params):
            if isinstance(param, str):
                if param != cleaned_args[i]:
                    return False
            elif isinstance(param, Choices):
                if cleaned_args[i] not in param.options:
                    return False
            elif isinstance(param, Value):
                if param.python_type is not str:
                    try:
                        param.python_type(cleaned_args[i])
                    except ValueError:
                        return False
            elif isinstance(param, Args):
                break
            else:
                raise RuntimeError('Unknown parameter type')

        if self._str_flags != outer_command.get_cleaned_flags():
            return False

        return True

    @cached_property
    def _str_flags(self) -> set[str]:
        return {flag.name for flag in self.flags}

    def to_str(self) -> str:
        result = self.name

        if self.params:
            str_params = (
                param.to_str() if isinstance(param, BaseParam) else param
                for param in self.params
            )
            result += f' {" ".join(str_params)}'

        if self.flags:
            result += f' {" ".join(flag.to_str() for flag in self.flags)}'

        return f'`{escape_markdown(result)}`'


class BaseParam(abc.ABC):
    @abc.abstractmethod
    def to_str(self) -> str:
        pass


class Value(BaseParam):
    name: str
    python_type: typing.Type

    def __init__(self, name: str, *, python_type: typing.Type = str) -> None:
        self.name = name
        self.python_type = python_type

    def to_str(self) -> str:
        return f'<{self.name}:{self.python_type.__name__}>'


class Args(BaseParam):
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def to_str(self) -> str:
        return f'<{self.name} ...>'


class Choices(BaseParam):
    options: tuple[str, ...]

    def __init__(self, *options: str) -> None:
        self.options = options

    def to_str(self) -> str:
        return f'[{"|".join(self.options)}]'


class Flag:
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def to_str(self) -> str:
        return f'-{self.name}'


def module(
    *,
    title: str,
    description: typing.Optional[str] = None,
    commands: tuple['Command', ...] = (),
    use_auto_mapping_for_commands: bool = False,
) -> typing.Callable:
    def wrapper(klass: typing.Type) -> typing.Type:
        klass.interface = Module(
            title=title,
            description=description,
            commands=(
                *commands,
                *(
                    method._command
                    for method_name, method in inspect.getmembers(klass, predicate=inspect.isfunction)
                    if hasattr(method, '_command')
                ),
            ),
            use_auto_mapping_for_commands=use_auto_mapping_for_commands,
        )

        return klass

    return wrapper


def command(
    name: str,
    *params: typing.Union['BaseParam', str],
    flags: tuple[Flag, ...] = (),
) -> typing.Callable:
    def wrapper(func: typing.Callable) -> typing.Callable:
        func._command = Command(
            name,
            *params,
            flags=flags,
            method_name=func.__name__,
        )

        return func

    return wrapper
