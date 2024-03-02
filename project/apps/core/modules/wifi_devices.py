from libs.messengers.utils import escape_markdown
from ..base import BaseModule, Command
from ..constants import (
    BotCommands,
)
from ...common import interface
from ...devices.dto import Device
from ...devices.utils import device_manager


__all__ = ('WiFiDevices',)


@interface.module(
    title='WiFiDevices',
    description='The module manages connected devices to WiFi.',
)
class WiFiDevices(BaseModule):
    @interface.command(BotCommands.WIFI_DEVICES)
    def _show_wifi_devices(self) -> None:
        text = '*Devices*'

        for device in device_manager.devices:
            text += (
                f'\n\n**Name:** `{escape_markdown(device.name or "")}`\n'
                f'**MAC:** `{escape_markdown(device.mac_address)}`\n'
                f'**Is defining:** {device.is_defining}'
            )

        self.messenger.send_message(text, use_markdown=True)

    @interface.command(
        '/delete_wifi_device',
        interface.Value('mac_address'),
    )
    def _delete_wifi_device(self, command: Command) -> None:
        mac_address = command.first_arg

        device_manager.set_devices([device for device in device_manager.devices if device.mac_address != mac_address])

        self.messenger.send_message('Deleted')

    @interface.command(
        '/update_wifi_device',
        interface.Value('mac_address'),
        interface.Value('name'),
        interface.Choices('true', 'false'),
    )
    def _update_wifi_device(self, command: Command) -> None:
        mac_address = command.first_arg
        name = command.second_arg
        is_defining = command.third_arg == 'true'

        to_update = mac_address in device_manager.smart_devices_map
        to_create = not to_update

        if to_create:
            device_manager.add_device(Device(mac_address=mac_address, name=name, is_defining=is_defining))
            self.messenger.send_message('Added')
        elif to_update:
            devices = device_manager.devices

            for device in devices:
                if device.mac_address != mac_address:
                    continue

                device.name = name
                device.is_defining = is_defining

            device_manager.set_devices(devices)
            self.messenger.send_message('Saved')
        else:
            self.messenger.send_message('Wrong data')
