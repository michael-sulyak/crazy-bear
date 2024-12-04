from libs.zigbee.base import BaseZigBeeDevice, SubscriptionOnStateOfZigBeeDeviceMixin


__all__ = ('AqaraWaterLeakSensor',)


class AqaraWaterLeakSensor(SubscriptionOnStateOfZigBeeDeviceMixin, BaseZigBeeDevice):
    pass
