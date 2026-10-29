import datetime

from ....config import SmartDeviceNames
from ...signals.models import Signal
from ..constants import LAST_CRITICAL_SITUATION_OCCURRED_AT
from .base import BaseSimpleSensorStateHandler


__all__ = ('WaterLeakSensorsHandler',)


class WaterLeakSensorsHandler(BaseSimpleSensorStateHandler):
    device_names = SmartDeviceNames.WATER_LEAK_SENSORS

    def handle_sensor_state(self, *, state: dict, device_name: str, received_at: datetime.datetime) -> None:
        water_leak = state.get('water_leak', False)

        if water_leak:
            self._messenger.send_message(f'Detected water leak!\nSensor: {device_name}')
            self._state[LAST_CRITICAL_SITUATION_OCCURRED_AT] = datetime.datetime.now()

        Signal.add(signal_type=device_name, value=int(water_leak), received_at=received_at)

        self._check_battery(state['battery'], device_name=device_name)
