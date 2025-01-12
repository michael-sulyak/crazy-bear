import threading
from functools import cached_property, partial

from libs.casual_utils.parallel_computing import synchronized_method
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from project.config import SmartDeviceNames

from ...signals.models import Signal
from .base import BaseSignalHandler
from .mixins import ZigBeeDeviceBatteryCheckerMixin


__all__ = ('WaterLeakSensorsHandler',)


class WaterLeakSensorsHandler(ZigBeeDeviceBatteryCheckerMixin, BaseSignalHandler):
    device_names = (SmartDeviceNames.WATER_LEAK_SENSOR_WC_OPEN,)
    _lock: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()

        for sensor in self._sensors:
            sensor.subscribe_on_update(partial(self._process_update, device_name=sensor.friendly_name))

    def disable(self) -> None:
        for sensor in self._sensors:
            sensor.unsubscribe()

    @cached_property
    def _sensors(self) -> tuple[ZigBeeDeviceWithOnlyState, ...]:
        return tuple(
            self._context.smart_devices_map[device_name]
            for device_name in self.device_names
        )

    @synchronized_method
    def _process_update(self, state: dict, *, device_name: str) -> None:
        water_leak = state.get('water_leak', False)

        if water_leak:
            self._messenger.send_message(f'Detected water leak!\nSensor: {device_name}')

        Signal.add(signal_type=device_name, value=int(water_leak))

        self._check_battery(state['battery'], device_name=device_name)
