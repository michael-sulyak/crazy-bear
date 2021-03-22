import json
import os
import typing
from types import MappingProxyType


class NOTHING:
    pass


class Env:
    def __call__(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        if default is NOTHING:
            return os.environ[name]
        else:
            return os.environ.get(name, default)

    def int(self, name: str, *, default: typing.Any = NOTHING) -> typing.Optional[int]:
        result = self(name, default=default)

        if not result and result != 0:
            return None

        return int(result)

    def float(self, name: str, *, default: typing.Any = NOTHING) -> typing.Optional[float]:
        result = self(name, default=default)

        if not result and result != 0:
            return None

        return float(result)

    def bool(self, name: str, *, default: typing.Any = NOTHING) -> typing.Optional[int]:
        result = self(name, default=default)
        return result in ('1', 'true', 'True', 'yes', 'YES',)

    def tuple(self,
              name: str, *,
              default: typing.Any = NOTHING,
              separator: str = ',',
              value_type: typing.Any = str) -> tuple:
        result = self(name, default=default)

        if not result:
            return ()

        return tuple(value_type(x) for x in result.split(separator))

    def frozenset(self,
                  name: str, *,
                  default: typing.Any = NOTHING,
                  separator: str = ',',
                  value_type: typing.Any = str) -> frozenset:
        result = self.tuple(name, default=default, separator=separator, value_type=value_type)
        return frozenset(result)

    def json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        result = self(name, default=default)

        if not result:
            return None

        return json.loads(result)

    def frozen_json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        data = self.json(name, default=default)

        if data is None:
            return None

        return MappingProxyType(data)


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
