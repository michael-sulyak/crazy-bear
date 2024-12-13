import threading
from functools import partial

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.messengers.utils import escape_markdown
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from project.config import SmartDeviceNames

from .base import BaseSignalHandler
from .mixins import ZigBeeDeviceBatteryCheckerMixin


__all__ = ('DoorSensorsHandler',)


class DoorSensorsHandler(ZigBeeDeviceBatteryCheckerMixin, BaseSignalHandler):
    device_names = (SmartDeviceNames.DOOR_SENSOR_NARNIA,)
    _last_contact_statuses_map: dict[str, bool]
    _lock: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._last_contact_statuses_map = {}
        self._lock = threading.RLock()

        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.subscribe_on_update(partial(self._process_update, device_name=device_name))

    def disable(self) -> None:
        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.unsubscribe()

    @synchronized_method
    def _process_update(self, state: dict, *, device_name: str) -> None:
        now = get_current_time()
        current_contact_status = state['contact']
        previous_contact_status = self._last_contact_statuses_map.get(device_name)
        is_initialization_status = current_contact_status and previous_contact_status is None

        if current_contact_status != previous_contact_status:
            self._last_contact_statuses_map[device_name] = current_contact_status

            if not is_initialization_status:
                str_status = 'has been closed' if current_contact_status else 'has been opened'

                self._messenger.send_message(
                    (
                        f'*Door "{escape_markdown(device_name)}" {str_status}*\n'
                        f'Timestamp: `{escape_markdown(now.strftime("%Y-%m-%d, %H:%M:%S"))}`'
                    ),
                    use_markdown=True,
                )

        self._check_battery(state['battery'], device_name=device_name)
