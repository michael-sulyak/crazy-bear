import threading
import typing

from .dto import Device
from ..common.routers.utils import get_connected_macs_to_router
from ..dynamic_config.events import dynamic_config_is_updated
from ..dynamic_config.utils import dynamic_config


class DeviceManager:
    _lock: threading.RLock
    _devices: typing.Optional[tuple[Device, ...]] = None
    _devices_map: typing.Optional[typing.Dict[str, Device]] = None

    def __init__(self) -> None:
        self._lock = threading.RLock()
        dynamic_config_is_updated.connect(self.clear_cache)

    def add_device(self, device: Device) -> None:
        with self._lock:
            raw_mac_addresses = self.get_raw_devices()

            if raw_mac_addresses is None:
                raw_mac_addresses = []

            dynamic_config['devices'] = [*raw_mac_addresses, device.to_dict()]

    def set_devices(self, devices: typing.Iterable[Device]) -> None:
        with self._lock:
            dynamic_config['devices'] = [device.to_dict() for device in devices]

    @property
    def devices(self) -> tuple[Device, ...]:
        with self._lock:
            if self._devices is None:
                self._devices = tuple(
                    Device.from_dict(raw_mac_addresses)
                    for raw_mac_addresses in self.get_raw_devices()
                )

            return self._devices

    @property
    def devices_map(self) -> typing.Dict[str, Device]:
        with self._lock:
            if self._devices_map is None:
                self._devices_map = {}

                for device in self.devices:
                    self.devices_map[device.mac_address] = device

            return self._devices_map

    def clear_cache(self) -> None:
        with self._lock:
            self._devices = None
            self._devices_map = None

    @staticmethod
    def get_raw_devices() -> typing.List[dict]:
        raw_devices = dynamic_config['devices']

        if raw_devices is None:
            raw_devices = []

        return raw_devices


device_manager = DeviceManager()


def get_connected_devices_to_router() -> typing.Generator[Device, None, None]:
    mac_addresses_map = device_manager.devices_map

    for mac in get_connected_macs_to_router():
        if mac in mac_addresses_map:
            yield mac_addresses_map[mac]
        else:
            yield Device(mac_address=mac)


def check_if_host_is_at_home() -> bool:
    return any(device.is_defining for device in get_connected_devices_to_router())
