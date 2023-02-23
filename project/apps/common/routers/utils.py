import logging
import typing

from .mi import mi_wifi
from .tplink import TpLink
from .... import config


def get_connected_macs_to_router() -> typing.Generator[str, None, None]:
    if config.ROUTER_TYPE == 'tplink':
        tplink = TpLink(
            username=config.ROUTER_USERNAME,
            password=config.ROUTER_PASSWORD,
            url=config.ROUTER_URL,
        )

        try:
            connected_devices = tplink.get_connected_devices()
        except Exception as e:
            logging.exception(e)
            return

        for device in connected_devices:
            mac_address = device.get('MACAddress')

            if mac_address:
                yield mac_address
    elif config.ROUTER_TYPE == 'mi':
        connected_devices = mi_wifi.device_list()['list']

        for device in connected_devices:
            yield device['mac']
    else:
        raise RuntimeError(f'Unexpected router type ({config.ROUTER_TYPE})')
