from . import constants


class BaseSmartDevice:
    friendly_name: str
    device_type: constants.SmartDeviceType
