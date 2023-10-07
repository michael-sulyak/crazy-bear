import typing

from .mi import mi_wifi


def get_connected_macs_to_router() -> typing.Generator[str, None, None]:
    connected_devices = mi_wifi.device_list()['list']

    for device in connected_devices:
        yield device['mac']
