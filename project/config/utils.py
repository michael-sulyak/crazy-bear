import os
import typing


class NOTHING:
    pass


class Env:
    def __call__(self, name: str, default: typing.Any = NOTHING) -> typing.Any:
        if default is NOTHING:
            return os.environ[name]
        else:
            return os.environ.get(name, default)

    def int(self, *args, **kwargs) -> typing.Optional[int]:
        result = self(*args, **kwargs)

        if not result and result != 0:
            return None

        return int(result)

    def float(self, *args, **kwargs) -> typing.Optional[float]:
        result = self(*args, **kwargs)

        if not result and result != 0:
            return None

        return float(result)

    def bool(self, *args, **kwargs) -> typing.Optional[int]:
        result = self(*args, **kwargs)
        return result in ('1', 'true',)


env = Env()


class VersionConfig:
    version: str
    parsed_version: typing.Tuple[int, int, int]
    major: int
    minor: int
    patch: int

    def __init__(self):
        with open('./VERSION', 'r') as file:
            self.version = file.readline().strip()
            self.parsed_version = tuple(int(n) for n in self.version.split('.'))
            self.major, self.minor, self.patch = self.parsed_version
