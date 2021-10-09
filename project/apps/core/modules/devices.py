import typing

from ..base import BaseModule, Command
from ..constants import (
    BotCommands,
)
from ...devices.dto import Device
from ...devices.utils import device_manager


__all__ = (
    'Devices',
)


class Devices(BaseModule):
    def process_command(self, command: Command) -> typing.Any:
        if command.name != BotCommands.DEVICES:
            return False

        if not command.first_arg:
            text = '*Devices*'

            for device in device_manager.devices:
                text += (
                    f'\n\n**Name:** {device.name}\n'
                    f'**MAC:** {device.mac_address}\n'
                    f'**Is defining:** {device.is_defining}'
                )

            self.messenger.send_message(text)

            return True

        mac_address = command.first_arg
        name = command.second_arg
        is_defining = command.third_arg == 'true'

        if mac_address in device_manager.devices_map:
            devices = device_manager.devices

            for device in devices:
                if device.mac_address != mac_address:
                    continue

                device.name = name
                device.is_defining = is_defining

            device_manager.set_devices(devices)
        else:
            device_manager.add_device(Device(mac_address=mac_address, name=name, is_defining=is_defining))

        self.messenger.send_message('Added')

        return True
