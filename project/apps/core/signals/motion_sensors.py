import datetime
import io
import threading
import typing
from functools import partial

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.messengers.utils import escape_markdown
from libs.zigbee.devices import ZigBeeDeviceWithOnlyState
from project.config import SmartDeviceNames

from ...common.utils import create_plot, interpolate_old_values_for_stats, with_throttling
from ...signals.models import Signal
from ..constants import SECURITY_IS_ENABLED, MotionTypeSources
from ..events import motion_detected
from .base import BaseSignalHandler
from .mixins import ZigBeeDeviceBatteryCheckerMixin


__all__ = ('MotionSensorsHandler',)

OCCUPANCY = 'occupancy'


class MotionSensorsHandler(ZigBeeDeviceBatteryCheckerMixin, BaseSignalHandler):
    device_names = (SmartDeviceNames.MOTION_SENSOR_HALLWAY,)
    _last_occupancy: bool | None = None
    _lock: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()

        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.subscribe_on_update(partial(self._process_update, device_name=device_name))

    def disable(self) -> None:
        for device_name in self.device_names:
            sensor: ZigBeeDeviceWithOnlyState = self._context.smart_devices_map[device_name]
            sensor.unsubscribe()

    def generate_plots(
        self,
        *,
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> typing.Sequence[io.BytesIO] | None:
        stats = Signal.get(OCCUPANCY, datetime_range=date_range)
        plots = []

        if stats:
            stats = interpolate_old_values_for_stats(
                x_attr='received_at',
                y_attr='value',
                x_atom=datetime.timedelta(microseconds=1),
                stats=stats,
            )
            plots.append(create_plot(title='Motion sensor', x_attr='received_at', y_attr='value', stats=stats))

        return plots

    @synchronized_method
    def _process_update(self, state: dict, *, device_name: str) -> None:
        occupancy = state['occupancy']

        now = get_current_time()

        Signal.add(signal_type=OCCUPANCY, value=1 if occupancy else 0, received_at=now)

        if self._state[SECURITY_IS_ENABLED]:
            if self._last_occupancy != occupancy:
                self._last_occupancy = occupancy

                if occupancy:
                    motion_detected.send(source=MotionTypeSources.SENSORS)
                    self._send_message_about_movement(received_at=now)
        else:
            self._last_occupancy = None

        self._check_battery(state['battery'], device_name=device_name)

    @with_throttling(datetime.timedelta(seconds=5), count=1)
    def _send_message_about_movement(self, *, received_at: datetime.datetime) -> None:
        self._messenger.send_message(
            (
                f'*Detected movement*\n'
                f'Timestamp: `{escape_markdown(received_at.strftime("%Y-%m-%d, %H:%M:%S"))}`'
            ),
            use_markdown=True,
        )
