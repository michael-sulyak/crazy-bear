import datetime

from ....config import SmartDeviceNames
from ...signals.models import Signal
from ..constants import LAST_CRITICAL_SITUATION_OCCURRED_AT
from .base import BaseSimpleSensorStateHandler


__all__ = ('SmokeDetectorsHandler',)


class SmokeDetectorsHandler(BaseSimpleSensorStateHandler):
    device_names = SmartDeviceNames.SMOKE_DETECTORS

    def handle(self, *, state: dict, device_name: str, received_at: datetime.datetime) -> None:
        has_smoke = state.get('smoke', False)
        is_test = state.get('test', False)

        if has_smoke or is_test:
            self._messenger.send_message(f'Detected smoke!\nSensor: {device_name}')
            self._state[LAST_CRITICAL_SITUATION_OCCURRED_AT] = datetime.datetime.now()

        Signal.add(signal_type=device_name, value=int(has_smoke), received_at=received_at)

        self._check_battery(state['battery'], device_name=device_name)
