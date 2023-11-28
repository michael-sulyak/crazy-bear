import datetime
import os
import re


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
        year = now.year % 1_000
        month = now.month

        if self.major != year or self.minor != month:
            self.major, self.minor, self.patch = year, month, 1
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
