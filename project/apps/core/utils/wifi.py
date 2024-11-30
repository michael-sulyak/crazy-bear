import typing
from dataclasses import dataclass

from .... import config
from ...common.routers.utils import get_connected_macs_to_router


@dataclass(frozen=True)
class WifiDevice:
    mac_address: str
    name: str | None = None
    is_defining: bool = False


WIFI_DEVICES_MAP = {item['mac_address']: WifiDevice(**item) for item in config.WIFI_DEVICES}


def get_connected_devices_to_router() -> typing.Generator[WifiDevice, None, None]:
    for mac in get_connected_macs_to_router():
        if mac in WIFI_DEVICES_MAP:
            yield WIFI_DEVICES_MAP[mac]
        else:
            yield WifiDevice(mac_address=mac)


def check_if_host_is_at_home() -> bool:
    return any(device.is_defining for device in get_connected_devices_to_router())
