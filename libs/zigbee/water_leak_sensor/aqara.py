import threading
import typing

from libs.casual_utils.parallel_computing import synchronized_method
from libs.zigbee.base import BaseZigBeeDevice


__all__ = ('AqaraWaterLeakSensor',)


class AqaraWaterLeakSensor(BaseZigBeeDevice):
    _lock: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()

    @synchronized_method
    def subscribe_on_update(self, func: typing.Callable) -> None:
        self.zig_bee.subscribe_on_state(self.friendly_name, lambda name, state: func(state))

    @synchronized_method
    def unsubscribe(self) -> None:
        self.zig_bee.unsubscribe_from_state(self.friendly_name)
