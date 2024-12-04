from libs.zigbee.base import BaseZigBeeDevice, SubscriptionOnStateOfZigBeeDeviceMixin


__all__ = ('TuyaMotionSensor',)


class TuyaMotionSensor(SubscriptionOnStateOfZigBeeDeviceMixin, BaseZigBeeDevice):
    pass
