from libs.messengers.utils import escape_markdown

from ...common import interface
from ...common.routers.tplink import tplink_router
from ...core import constants
from ..base import BaseModule


__all__ = ('Router',)


@interface.module(
    title='Router',
    description='The module provides an integration with a router.',
)
class Router(BaseModule):
    @interface.command(constants.BotCommands.RAW_WIFI_DEVICES)
    def _show_wifi_connected_devices(self) -> None:
        message = ''
        device_fields = (
            'type',
            'macaddr',
            'hostname',
            'packets_sent',
            'packets_received',
            'down_speed',
            'up_speed',
            'ipaddr',
        )

        for device in tplink_router.get_devices():
            for device_field in device_fields:
                message += f'*{escape_markdown(device_field)}:* {escape_markdown(str(getattr(device, device_field)))}\n'

            message += '\n'

        self.messenger.send_message(message, use_markdown=True)
