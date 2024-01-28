import typing

from ..base import BaseModule, Command
from ...common import interface


__all__ = (
    'ZigBeeController',
)


@interface.module(
    title='ZigBee',
    description=(
        'The module manages ZigBee devices.'
    ),
)
class ZigBeeController(BaseModule):
    def process_command(self, command: Command) -> typing.Any:
        if command.name == '/zigbee':
            self._show_status()
            return True

        return False

    @interface.command('/zigbee')
    def _show_status(self) -> None:
        self.messenger.send_message(f'Is health: {self.context.zig_bee.is_health()}')

        devices_info = []

        for device in self.context.zig_bee.devices:
            if device['type'] == 'Coordinator':
                devices_info.append(f'Coordinator\nIs disabled: {device["disabled"]}')
                continue

            devices_info.append(
                f'Friendly name: {device["friendly_name"]}\n'
                f'IEEE address: {device["ieee_address"]}\n'
                f'Power source: {device["power_source"]}\n'
                f'Supported: {device["supported"]}\n'
                f'Type: {device["type"]}\n'
            )

        devices_info = '\n\n'.join(devices_info)

        self.messenger.send_message(f'Devices\n\n{devices_info}')

        temporary_subscribers = '\n'.join(self.context.zig_bee._temporary_subscribers_map.keys())
        self.messenger.send_message(f'Temporary subscribers:\n```\n{temporary_subscribers}\n```')

        permanent_subscribers = '\n'.join(self.context.zig_bee._permanent_subscribers_map.keys())
        self.messenger.send_message(f'Permanent subscribers:\n```\n{permanent_subscribers}\n```')

        self.messenger.send_message(f'Availability map:\n```\n{self.context.zig_bee._availability_map}\n```')
