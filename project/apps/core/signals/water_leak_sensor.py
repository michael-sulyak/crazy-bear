import datetime
from functools import partial

from libs.zigbee.water_leak_sensor.aqara import AqaraWaterLeakSensor
from project.config import SmartDeviceNames
from .base import BaseSignalHandler
from .utils import get_default_signal_compress_datetime_range
from ...signals.models import Signal


__all__ = ('WaterLeakSensorHandler',)


class WaterLeakSensorHandler(BaseSignalHandler):
    device_names = (
        SmartDeviceNames.WATER_LEAK_SENSOR_WC_OPEN,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        for device_name in self.device_names:
            sensor: AqaraWaterLeakSensor = self._context.smart_devices_map[device_name]  # noqa
            sensor.subscribe_on_update(partial(self._process_update, device_name=device_name))

    def compress(self) -> None:
        signal_types = self.device_names
        Signal.clear(signal_types)

        datetime_range = get_default_signal_compress_datetime_range()

        for signal_type in signal_types:
            Signal.compress(
                signal_type,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )

    def disable(self) -> None:
        for device_name in self.device_names:
            sensor: AqaraWaterLeakSensor = self._context.smart_devices_map[device_name]  # noqa
            sensor.unsubscribe()

    def _process_update(self, state: dict, *, device_name: str) -> None:
        water_leak = state['water_leak']

        if water_leak:
            self._messenger.send_message(f'Detected water leak!\nSensor: {device_name}')

        Signal.add(signal_type=device_name, value=int(water_leak))
