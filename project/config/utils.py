import datetime
import json
import os
import re
import typing
from types import MappingProxyType

from crontab import CronTab


class NOTHING:
    pass


class Env:
    def __call__(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        if default is NOTHING:
            return os.environ[name]
        else:
            return os.environ.get(name, default)

    def int(self, name: str, *, default: typing.Any = NOTHING) -> int | None:
        return self._value(name, default=default, value_converter=int)

    def float(self, name: str, *, default: typing.Any = NOTHING) -> float | None:
        return self._value(name, default=default, value_converter=float)

    def bool(self, name: str, *, default: typing.Any = NOTHING) -> bool | None:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        is_true = result in ('1', 'true', 'True', 'yes', 'YES',)

        if is_true:
            return True

        if result not in ('0', 'false', 'False', 'no', 'NO',):
            raise ValueError

        return False

    def tuple(self,
              name: str, *,
              default: typing.Any = NOTHING,
              separator: str = ',',
              value_type: typing.Any = str) -> tuple | None:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        if not result:
            return None

        return tuple(value_type(x.strip()) for x in result.split(separator))

    def frozen_set(self,
                   name: str, *,
                   default: typing.Any = NOTHING,
                   separator: str = ',',
                   value_type: typing.Any = str) -> typing.Optional[frozenset]:
        result = self.tuple(name, default=default, separator=separator, value_type=value_type)

        if result is None:
            return result

        return frozenset(result)

    def json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        return self._value(name, default=default, value_converter=json.loads)

    def frozen_json(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        data = self.json(name, default=default)

        if data is None:
            return None

        return MappingProxyType(data)

    def time_delta(self, name: str, *, default: typing.Any = NOTHING) -> datetime.timedelta:
        try:
            result = self.tuple(name, separator=' ')
        except KeyError:
            if default is NOTHING:
                raise

            return default

        assert result is not None

        return datetime.timedelta(**{result[1]: int(result[0])})

    def range(self,
              name: str, *,
              default: typing.Any = NOTHING,
              value_type: typing.Callable) -> typing.Tuple[typing.Any, typing.Any]:
        try:
            result = self.tuple(name, value_type=value_type)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        assert result is not None

        if len(result) != 2:
            raise ValueError

        return result  # type: ignore

    def time_range(self, name: str, *, default: typing.Any = NOTHING) -> typing.Tuple[datetime.time, datetime.time]:
        return self.range(name, default=default, value_type=datetime.time.fromisoformat)

    def crontab(self, name: str, *, default: typing.Any = NOTHING) -> typing.Any:
        return self._value(name, default=default, value_converter=CronTab)

    def _value(self,
               name: str, *,
               default: typing.Any = NOTHING,
               value_converter: typing.Callable) -> typing.Any:
        try:
            result = self(name)
        except KeyError:
            if default is NOTHING:
                raise

            return default

        return value_converter(result)


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
    def parsed_version(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    def increase(self) -> None:
        """
        `YY.MM.MICRO` style, where:
            * `YY` - Short year - 6, 16, 106;
            * `MM` - Short month - 1, 2 ... 11, 12;
            * `MICRO` - Version in the month.
        """

        now = datetime.datetime.now(datetime.timezone.utc)

        if self.major != now.year or self.minor != now.month:
            self.major, self.minor, self.patch = now.year, now.month, 1
        else:
            self.patch += 1

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

        assert version_match is not None

        return version_match
