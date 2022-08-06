import abc
import typing


def generate_doc(*, title: str, commands: tuple['CommandDef', ...]) -> str:
    commands = '\n'.join(command.to_short_form() for command in commands)

    return f'*{title}*\n{commands}'


class CommandDef:
    name: str
    params: tuple
    flags: tuple['FlagDef', ...]

    def __init__(self, name: str, *params: typing.Union['BaseParam', str], flags: tuple['FlagDef', ...] = ()) -> None:
        self.name = name
        self.params = params
        self.flags = flags

    def to_short_form(self) -> str:
        result = self.name

        if self.params:
            str_params = (
                param.to_short_form() if isinstance(param, BaseParam) else param
                for param in self.params
            )
            result += f' {" ".join(str_params)}'

        if self.flags:
            result += f' {" ".join(flag.to_short_form() for flag in self.flags)}'

        return result


class BaseParam(abc.ABC):
    @abc.abstractmethod
    def to_short_form(self) -> str:
        pass


class VarDef(BaseParam):
    name: str
    type: str

    def __init__(self, name: str, *, type: str = 'str') -> None:
        self.name = name
        self.type = type

    def to_short_form(self) -> str:
        return f'<{self.name}:{self.type}>'


class OptionsDef(BaseParam):
    options: tuple[str, ...]

    def __init__(self, *options: str) -> None:
        self.options = options

    def to_short_form(self) -> str:
        return f'\\[{"|".join(self.options)}\\]'


class FlagDef:
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def to_short_form(self) -> str:
        return f'-{self.name}'
