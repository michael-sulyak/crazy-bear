import datetime
import logging
import typing
from functools import cached_property

from emoji.core import emojize

from libs.casual_utils.time import get_current_time
from libs.messengers.utils import escape_markdown
from ..constants import (
    ARDUINO_IS_ENABLED,
    AUTO_SECURITY_IS_ENABLED,
    CAMERA_IS_AVAILABLE,
    CURRENT_FPS,
    SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
    VIDEO_SECURITY_IS_ENABLED,
)
from ...arduino.constants import ArduinoSensorTypes
from ...common.constants import INITED_AT
from ...common.exceptions import Shutdown
from ...common.state import State
from ...common.utils import get_cpu_temp, get_effective_temperature, get_free_disk_space, get_ram_usage
from ...devices.dto import Device
from ...devices.utils import get_connected_devices_to_router
from ...signals.models import Signal
from .... import config


class ShortTextReport:
    YES = emojize(':check_mark_button:')
    NO = emojize(':multiply:')
    NOTHING = emojize(':multiply:')

    state: State
    now: datetime.datetime
    _datetime_range_for_second_aggregation: tuple[datetime.datetime, datetime.datetime]

    def __init__(self, *, state: State) -> None:
        self.state = state
        self.now = get_current_time()
        self._datetime_range_for_second_aggregation = (
            self.now - datetime.timedelta(minutes=60),
            self.now,
        )

    def generate(self) -> str:
        camera_is_used = emojize(':camera_with_flash:') if self.state[USE_CAMERA] else ''
        video_recording_is_on = emojize(':film_frames:') if self.state[VIDEO_RECORDING_IS_ENABLED] else ''
        additional_camera_status = (
            f' {camera_is_used}{video_recording_is_on}' if camera_is_used or video_recording_is_on else ''
        )

        auto_security_is_enabled = (
            emojize(':counterclockwise_arrows_button:') if self.state[AUTO_SECURITY_IS_ENABLED] else ''
        )
        video_security_is_enabled = emojize(':film_frames:') if self.state[VIDEO_SECURITY_IS_ENABLED] else ''
        additional_security_status = (
            f'{auto_security_is_enabled}{video_security_is_enabled}'
            if auto_security_is_enabled or video_security_is_enabled
            else ''
        )

        return (
            f'️*Crazy Bear* `v{escape_markdown(config.VERSION)}`\n\n'
            f'{emojize(":floppy_disk:")} *Devices*\n'
            f'Arduino: {self.YES if self.state[ARDUINO_IS_ENABLED] else self.NO}\n'
            f'Camera: `{self.YES if self.state[CAMERA_IS_AVAILABLE] else self.NO}{additional_camera_status}'
            f'{f"FPS {escape_markdown(self._fps_info)}" if self.state[CAMERA_IS_AVAILABLE] else ""}`\n\n'
            f'{emojize(":shield:")} *Security*\n'
            f'Security: `{self.YES if self.state[SECURITY_IS_ENABLED] else self.NO}{additional_security_status}`\n\n'
            f'{emojize(":bar_chart:")} *Sensors*\n'
            f'Humidity: `{escape_markdown(self._humidity_info)}`\n'
            f'Temperature: `{escape_markdown(self._temperature_info)}`\n'
            f'Temperature\\*: `{escape_markdown(self._effective_temperature_info)}`\n'
            f'CPU Temperature: `{escape_markdown(self._cpu_temperature_info)}`\n'
            f'RAM usage: `{escape_markdown(self._ram_usage_info)}`\n'
            f'Free space: `{escape_markdown(self._free_space_info)}`\n\n'
            f'{emojize(":clipboard:")} *Other info*\n'
            f'WiFi: {self._connected_devices_info}\n'
            f'Started at: `{escape_markdown(self.state[INITED_AT].strftime("%d.%m.%Y, %H:%M:%S"))}`'
        )

    @cached_property
    def _humidity(self) -> typing.Optional[float]:
        return Signal.get_one_aggregated(ArduinoSensorTypes.HUMIDITY)

    @cached_property
    def _second_humidity(self) -> typing.Optional[float]:
        return Signal.get_one_aggregated(
            ArduinoSensorTypes.HUMIDITY,
            datetime_range=self._datetime_range_for_second_aggregation,
        )

    @cached_property
    def _temperature(self) -> typing.Optional[float]:
        return Signal.get_one_aggregated(ArduinoSensorTypes.TEMPERATURE)

    @cached_property
    def _second_temperature(self) -> typing.Optional[float]:
        return Signal.get_one_aggregated(
            ArduinoSensorTypes.TEMPERATURE,
            datetime_range=self._datetime_range_for_second_aggregation,
        )

    @property
    def _humidity_info(self) -> str:
        if self._humidity is None:
            return self.NOTHING

        humidity_info = f'{round(self._humidity, 1)}%{self._get_mark(self._humidity, (30, 45.5,), (30, 60.5,))}'

        if self._second_humidity is not None:
            diff = round(self._humidity - self._second_humidity, 1)

            if diff != 0:
                humidity_info += f' ({"+" if diff > 0 else ""}{diff})'

        return humidity_info

    @property
    def _temperature_info(self) -> str:
        if self._temperature is None:
            return self.NOTHING

        temperature_info = (
            f'{round(self._temperature, 1)}℃{self._get_mark(self._temperature, (20, 22.5,), (18, 24.5,))}'
        )

        if self._second_temperature is not None:
            diff = round(self._temperature - self._second_temperature, 1)

            if diff != 0:
                temperature_info += f' ({"+" if diff > 0 else ""}{diff})'

        return temperature_info

    @property
    def _effective_temperature_info(self) -> str:
        if self._temperature is None or self._humidity is None:
            return self.NOTHING

        temperature = get_effective_temperature(
            temperature=self._temperature,
            humidity=self._humidity,
        )

        temperature_info = f'{round(temperature, 1)}℃{self._get_mark(temperature, (18, 22.5,), (16, 26.5,))}'

        if self._second_temperature is not None and self._second_humidity is not None:
            second_temperature = get_effective_temperature(
                temperature=self._second_temperature,
                humidity=self._second_humidity,
            )
        else:
            second_temperature = None

        if second_temperature is not None:
            diff = round(temperature - second_temperature, 1)

            if diff != 0:
                temperature_info += f' ({"+" if diff > 0 else ""}{diff})'

        return temperature_info

    @property
    def _fps_info(self) -> str:
        current_fps = self.state[CURRENT_FPS]

        if current_fps is None:
            return self.NOTHING

        return str(round(self.state[CURRENT_FPS], 2))

    @property
    def _connected_devices_info(self) -> str:
        connected_devices: tuple[Device, ...] = ()

        try:
            connected_devices = tuple(get_connected_devices_to_router())
        except Shutdown:
            raise
        except Exception as e:
            logging.exception(e)

        if not connected_devices:
            return self.NOTHING

        return ', '.join(
            f'`{escape_markdown(device.name)}`' if device.name else f'`Unknown {escape_markdown(device.mac_address)}`'
            for device in connected_devices
        )

    @property
    def _ram_usage_info(self) -> str:
        ram_usage = get_ram_usage() * 100
        return f'{round(ram_usage, 1)}%{self._get_mark(ram_usage, (0, 60,), (0, 80,))}'

    @property
    def _free_space_info(self) -> str:
        free_space = get_free_disk_space() / 1024
        mark = self._get_mark(
            free_space,
            (
                1,
                float("inf"),
            ),
            (
                0.5,
                float("inf"),
            ),
        )
        return f'{round(free_space, 2)}GB {mark}'

    @property
    def _cpu_temperature_info(self) -> str:
        try:
            cpu_temperature = get_cpu_temp()
        except RuntimeError:
            cpu_temperature_info = self.NOTHING
        else:
            cpu_temperature_info = f'{round(cpu_temperature, 1)}℃{self._get_mark(cpu_temperature, (0, 60,), (0, 80,))}'

        return cpu_temperature_info

    @staticmethod
    def _get_mark(value: float, good_range: tuple[float, float], acceptable_range: tuple[float, float]) -> str:
        is_not_acceptable = not (acceptable_range[0] <= value <= acceptable_range[1])

        if is_not_acceptable:
            return emojize(':red_exclamation_mark:')

        is_not_good = not (good_range[0] <= value <= good_range[1])

        if is_not_good:
            return emojize(':white_exclamation_mark:')

        return ''
