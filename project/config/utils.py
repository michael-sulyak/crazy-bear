import datetime
import json
import os
import re
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
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        if not result and result != 0:
            return default

        return int(result)

    def float(self, name: str, *, default: typing.Any = NOTHING) -> typing.Optional[float]:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        if not result and result != 0:
            return default

        return float(result)

    def bool(self, name: str, *, default: typing.Any = NOTHING) -> typing.Optional[int]:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        return result in ('1', 'true', 'True', 'yes', 'YES',)

    def tuple(self,
              name: str, *,
              default: typing.Any = NOTHING,
              separator: str = ',',
              value_type: typing.Any = str) -> typing.Optional[tuple]:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        if not result:
            return None

        return tuple(value_type(x) for x in result.split(separator))

    def frozenset(self,
                  name: str, *,
                  default: typing.Any = NOTHING,
                  separator: str = ',',
                  value_type: typing.Any = str) -> typing.Optional[frozenset]:
        result = self.tuple(name, default=default, separator=separator, value_type=value_type)

        if result is None:
            return result

        return frozenset(result)

    def json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        if not result:
            return None

        return json.loads(result)

    def frozen_json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        data = self.json(name, default=default)

        if data is None:
            return None

        return MappingProxyType(data)

    def timedelta(self, name: str, *, default: typing.Any = NOTHING) -> datetime.timedelta:
        try:
            result = self.tuple(name, separator=' ')
        except KeyError:
            if default is NOTHING:
                raise

            return default

        return datetime.timedelta(**{result[1]: int(result[0])})


env = Env()


class VersionDetails:
    major: int
    minor: int
    patch: int
    _filename_with_version = os.path.join(os.path.dirname(__file__), '../../__init__.py')

    def __init__(self) -> None:
        version = self._get_version()
        parsed_version = tuple(int(n) for n in version.split('.'))
        self.major, self.minor, self.patch = parsed_version

    def __repr__(self) -> str:
        return f'Version {self.version}'

    @property
    def version(self) -> str:
        return f'{self.major}.{self.minor}.{self.patch}'

    @property
    def parsed_version(self) -> typing.Tuple[int, int, int]:
        return self.major, self.minor, self.patch

    def save(self) -> None:
        version_line = self._get_version_match().group(0)

        with open(self._filename_with_version, 'r') as file:
            file_data = file.read()

        with open(self._filename_with_version, 'w') as file:
            file_data = file_data.replace(version_line, f'__version__ = \'{self.version}\'')
            file.write(file_data)

    def _get_version(self) -> str:
        version_match = self._get_version_match()

        if version_match:
            return version_match.group(1)

        raise RuntimeError('Unable to find version string.')

    def _get_version_match(self) -> re.Match:
        with open(self._filename_with_version) as file:
            version_file = file.read()

        version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)

        return version_match
