import abc
import dataclasses
import typing

from ..messengers.utils import escape_markdown


@dataclasses.dataclass
class Doc:
    title: str
    description: typing.Optional[str] = None
    commands: tuple['CommandDef', ...] = ()

    def to_str(self) -> str:
        result = f'*{escape_markdown(self.title)}*'

        if self.description:
            result += f'\n_{escape_markdown(self.description)}_'

        if self.commands:
            str_commands = '\n'.join(command.to_str() for command in self.commands)
            result += f'\n\n{str_commands}'

        return result


class CommandDef:
    name: str
    params: tuple
    flags: tuple['FlagDef', ...]

    def __init__(self, name: str, *params: typing.Union['BaseParam', str], flags: tuple['FlagDef', ...] = ()) -> None:
        self.name = name
        self.params = params
        self.flags = flags

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


class VarDef(BaseParam):
    name: str
    type: str

    def __init__(self, name: str, *, type: str = 'str') -> None:
        self.name = name
        self.type = type

    def to_str(self) -> str:
        return f'<{self.name}:{self.type}>'


class OptionsDef(BaseParam):
    options: tuple[str, ...]

    def __init__(self, *options: str) -> None:
        self.options = options

    def to_str(self) -> str:
        return f'[{"|".join(self.options)}]'


class FlagDef:
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def to_str(self) -> str:
        return f'-{self.name}'
