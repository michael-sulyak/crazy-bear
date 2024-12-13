import abc
import typing

from libs.smart_devices.base import BaseSmartDevice
from libs.smart_devices.constants import SmartDeviceType
from libs.zigbee.base import ZigBee


class BaseZigBeeDevice(BaseSmartDevice, abc.ABC):
    device_type = SmartDeviceType.ZIGBEE
    zig_bee: ZigBee

    def __init__(self, friendly_name: str, *, zig_bee: ZigBee) -> None:
        self.friendly_name = friendly_name
        self.zig_bee = zig_bee


class SubscriptionOnStateOfZigBeeDeviceMixin(abc.ABC):
    def subscribe_on_update(self, func: typing.Callable) -> None:
        self.zig_bee.subscribe_on_state(self.friendly_name, lambda name, state: func(state))

    def unsubscribe(self) -> None:
        self.zig_bee.unsubscribe_from_state(self.friendly_name)


class ZigBeeDeviceWithOnlyState(SubscriptionOnStateOfZigBeeDeviceMixin, BaseZigBeeDevice):
    pass
