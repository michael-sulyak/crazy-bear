import typing

from .tplink import tplink_router


def get_connected_macs_to_router() -> typing.Generator[str, None, None]:
    for device in tplink_router.get_devices():
        yield device.macaddr.replace('-', ':')
