from libs.zigbee.base import BaseZigBeeDevice, SubscriptionOnStateOfZigBeeDeviceMixin


__all__ = ('TuyaTemperatureHumiditySensor',)


class TuyaTemperatureHumiditySensor(SubscriptionOnStateOfZigBeeDeviceMixin, BaseZigBeeDevice):
    pass
