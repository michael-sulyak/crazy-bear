import datetime
import math
from functools import cached_property

from emoji.core import emojize

from libs.casual_utils.time import get_current_time
from libs.messengers.utils import escape_markdown
from .wifi import WifiDevice
from .. import constants
from ..constants import (
    AIR_MONITOR_CO2,
    AIR_MONITOR_HUMIDITY,
    AIR_MONITOR_TEMPERATURE,
    CAMERA_IS_AVAILABLE,
    CURRENT_FPS,
    SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
)
from ... import db
from ...common.constants import INITED_AT
from ...common.state import State
from ...common.utils import get_cpu_temp, get_effective_temperature, get_free_disk_space, get_ram_usage
from ...signals.models import Signal
from .... import config


class ShortTextReport:
    YES = emojize(':check_mark_button:')
    NO = emojize(':multiply:')
    NOTHING = emojize(':multiply:')
    UNKNOWN = emojize(':white_question_mark:')
    WARNING = emojize(':warning:')
    ALERT = emojize(':red_exclamation_mark:')

    SHIELD = emojize(':shield:')
    CHART = emojize(':bar_chart:')
    SYSTEM = emojize(':hammer_and_pick:')
    CLIPBOARD = emojize(':clipboard:')
    CROSS_MARK = emojize(':cross_mark:')

    MAX_CONNECTED_DEVICES_TO_SHOW = 8

    state: State
    now: datetime.datetime
    _datetime_range_for_hour_average: tuple[datetime.datetime, datetime.datetime]

    def __init__(self, *, state: State) -> None:
        self.state = state
        self.now = get_current_time()
        self._datetime_range_for_hour_average = (
            self.now - datetime.timedelta(hours=1),
            self.now,
        )

    def generate(self) -> str:
        return '\n'.join(
            [
                f'*Crazy Bear* `v{escape_markdown(str(config.VERSION))}`',
                '',
                f'{self.SHIELD} *Security*',
                f'Security: {self._code(self._security_summary)}',
                f'Camera: {self._code(self._camera_summary)}',
                '',
                f'{self.CHART} *Home*',
                f'Temp: {self._code(self._temperature_info)}',
                f'Feels: {self._code(self._effective_temperature_info)}',
                f'Humidity: {self._code(self._humidity_info)}',
                f'CO₂: {self._code(self._co2_info)}',
                '',
                f'{self.SYSTEM} *System*',
                f'CPU: {self._code(self._cpu_temperature_info)}',
                f'RAM: {self._code(self._ram_usage_info)}',
                f'Disk: {self._code(self._free_space_info)}',
                '',
                f'{self.CLIPBOARD} *Other*',
                f'WiFi: {self._connected_devices_info}',
                f'Started: {self._code(self._started_at_info)}',
            ]
        )

    @cached_property
    def _started_at(self) -> datetime.datetime | None:
        started_at = self._state_get(INITED_AT)

        if isinstance(started_at, datetime.datetime):
            return started_at

        return None

    @property
    def _started_at_info(self) -> str:
        if self._started_at is None:
            return self._unknown_info()

        return self._format_datetime(self._started_at)

    @property
    def _security_summary(self) -> str:
        return self._on_off(self._state_get(SECURITY_IS_ENABLED))

    @property
    def _camera_summary(self) -> str:
        camera_available = self._state_get(CAMERA_IS_AVAILABLE)

        if not camera_available:
            return self._on_off(camera_available)

        return (
            f'{self._on_off(camera_available)} · '
            f'View {self._on_off(self._state_get(USE_CAMERA))} · '
            f'Rec {self._on_off(self._state_get(VIDEO_RECORDING_IS_ENABLED))} · '
            f'FPS {self._fps_info}'
        )

    @cached_property
    def _humidity(self) -> float | None:
        return self._get_last_signal_value(AIR_MONITOR_HUMIDITY)

    @cached_property
    def _co2(self) -> float | None:
        return self._get_last_signal_value(AIR_MONITOR_CO2)

    @cached_property
    def _hour_average_humidity(self) -> float | None:
        return self._as_float(
            Signal.get_one_aggregated(
                AIR_MONITOR_HUMIDITY,
                datetime_range=self._datetime_range_for_hour_average,
            )
        )

    @cached_property
    def _temperature(self) -> float | None:
        return self._get_last_signal_value(AIR_MONITOR_TEMPERATURE)

    @cached_property
    def _hour_average_temperature(self) -> float | None:
        return self._as_float(
            Signal.get_one_aggregated(
                AIR_MONITOR_TEMPERATURE,
                datetime_range=self._datetime_range_for_hour_average,
            )
        )

    def _get_last_signal_value(self, signal_type: str) -> float | None:
        result = (
            db.get_db_session()
            .query(Signal.value)
            .filter(
                Signal.type == signal_type,
                Signal.received_at >= self.now - datetime.timedelta(minutes=30),
            )
            .order_by(Signal.received_at.desc())
            .limit(1)
            .first()
        )

        return result[0] if result else None

    @property
    def _humidity_info(self) -> str:
        if self._humidity is None:
            return self._no_data()

        humidity_info = f'{self._format_number(self._humidity, 1)}%'
        humidity_info += self._get_mark(self._humidity, (40, 60), (30, 70))
        humidity_info += self._format_delta(self._humidity, self._hour_average_humidity)

        return humidity_info

    @property
    def _temperature_info(self) -> str:
        if self._temperature is None:
            return self._no_data()

        temperature_info = f'{self._format_number(self._temperature, 1)} °C'
        temperature_info += self._get_mark(self._temperature, (18, 24), (16, 28))
        temperature_info += self._format_delta(self._temperature, self._hour_average_temperature)

        return temperature_info

    @property
    def _effective_temperature_info(self) -> str:
        if self._temperature is None or self._humidity is None:
            return self._no_data()

        temperature = self._as_float(
            get_effective_temperature(
                temperature=self._temperature,
                humidity=self._humidity,
            )
        )

        if temperature is None:
            return self._no_data()

        temperature_info = f'{self._format_number(temperature, 1)} °C'
        temperature_info += self._get_mark(temperature, (18, 24), (14, 28))

        if self._hour_average_temperature is not None and self._hour_average_humidity is not None:
            previous_temperature = self._as_float(
                get_effective_temperature(
                    temperature=self._hour_average_temperature,
                    humidity=self._hour_average_humidity,
                )
            )
            temperature_info += self._format_delta(temperature, previous_temperature)

        return temperature_info

    @property
    def _co2_info(self) -> str:
        if self._co2 is None:
            return self._no_data()

        co2_info = f'{round(self._co2)} ppm'
        co2_info += self._get_mark(self._co2, (0, 800), (0, 1_500))

        return co2_info

    @property
    def _fps_info(self) -> str:
        current_fps = self._as_float(self._state_get(CURRENT_FPS))

        if current_fps is None:
            return self._no_data()

        return self._format_number(current_fps, 2)

    @property
    def _connected_devices_info(self) -> str:
        connected_devices: tuple[WifiDevice, ...] | None = self._state_get(constants.CONNECTED_DEVICES_TO_ROUTER)

        if connected_devices is None:
            return self._code(self._unknown_info())

        if not connected_devices:
            return self._code('No devices')

        shown_devices = connected_devices[:self.MAX_CONNECTED_DEVICES_TO_SHOW]

        devices_info = [
            self._code(device.name if device.name else f'Unknown {device.mac_address}')
            for device in shown_devices
        ]

        hidden_count = len(connected_devices) - len(shown_devices)

        if hidden_count > 0:
            devices_info.append(self._code(f'+{hidden_count} more'))

        return ', '.join(devices_info)

    @property
    def _ram_usage_info(self) -> str:
        ram_usage = self._as_float(get_ram_usage())

        if ram_usage is None:
            return self._no_data()

        ram_usage *= 100

        return f'{self._format_number(ram_usage, 1)}%{self._get_mark(ram_usage, (0, 60), (0, 80))}'

    @property
    def _free_space_info(self) -> str:
        free_space = self._as_float(get_free_disk_space())

        if free_space is None:
            return self._no_data()

        free_space /= 1024

        free_space_info = f'{self._format_number(free_space, 2)} GB'
        free_space_info += self._get_mark(
            free_space,
            (
                1,
                math.inf,
            ),
            (
                0.5,
                math.inf,
            ),
        )

        return free_space_info

    @property
    def _cpu_temperature_info(self) -> str:
        try:
            cpu_temperature = self._as_float(get_cpu_temp())
        except RuntimeError:
            return self._no_data()

        if cpu_temperature is None:
            return self._no_data()

        cpu_temperature_info = f'{self._format_number(cpu_temperature, 1)} °C'
        cpu_temperature_info += self._get_mark(cpu_temperature, (0, 50), (0, 70))

        return cpu_temperature_info

    def _state_get(self, key: object, default: object | None = None) -> object | None:
        try:
            return self.state[key]
        except (KeyError, TypeError):
            return default

    @classmethod
    def _on_off(cls, value: object | None) -> str:
        if value is None:
            return cls._unknown_info()

        return cls.YES if value else cls.NO

    @classmethod
    def _no_data(cls) -> str:
        return cls.NOTHING

    @classmethod
    def _unknown_info(cls) -> str:
        return cls.UNKNOWN

    @staticmethod
    def _code(value: object) -> str:
        return f'`{escape_markdown(str(value))}`'

    @staticmethod
    def _format_datetime(value: datetime.datetime) -> str:
        return value.strftime('%d.%m.%Y, %H:%M:%S')

    @staticmethod
    def _format_number(value: float, digits: int = 1) -> str:
        return f'{value:.{digits}f}'

    @staticmethod
    def _format_delta(value: float | None, previous_value: float | None) -> str:
        value = ShortTextReport._as_float(value)
        previous_value = ShortTextReport._as_float(previous_value)

        if value is None or previous_value is None:
            return ''

        diff = round(value - previous_value, 1)

        if diff == 0:
            return ''

        return f' ({diff:+.1f})'

    @staticmethod
    def _as_float(value: object | None) -> float | None:
        if value is None:
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    @staticmethod
    def _get_mark(value: float, good_range: tuple[float, float], acceptable_range: tuple[float, float]) -> str:
        value = ShortTextReport._as_float(value)

        if value is None:
            return f' {ShortTextReport.UNKNOWN}'

        is_not_acceptable = not (acceptable_range[0] <= value <= acceptable_range[1])

        if is_not_acceptable:
            return f' {ShortTextReport.ALERT}'

        is_not_good = not (good_range[0] <= value <= good_range[1])

        if is_not_good:
            return f' {ShortTextReport.WARNING}'

        return ''
