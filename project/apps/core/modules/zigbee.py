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
    use_auto_mapping_for_commands=True,
)
class ZigBeeController(BaseModule):
    @interface.command('/zigbee_status')
    def _show_status(self, command: Command) -> None:
        self.messenger.send_message(f'Is health: `{self.context.zig_bee.is_health()}`', use_markdown=True)

        devices_info = '\n\n'.join(
            device.to_str()
            for device in self.context.zig_bee.devices
        )

        self.messenger.send_message(f'*Devices*\n\n{devices_info}', use_markdown=True)

        temporary_subscribers = '\n'.join(
            key
            for key, value in self.context.zig_bee._temporary_subscribers_map.items()
            if value
        )
        self.messenger.send_message(
            f'Temporary subscribers:\n```\n{temporary_subscribers or "-"}\n```',
            use_markdown=True,
        )

        permanent_subscribers = '\n'.join(
            key
            for key, value in self.context.zig_bee._permanent_subscribers_map.items()
            if value
        )
        self.messenger.send_message(
            f'Permanent subscribers:\n```\n{permanent_subscribers or "-"}\n```',
            use_markdown=True,
        )

        self.messenger.send_message(
            f'Availability map:\n```\n{self.context.zig_bee._availability_map or "-"}\n```',
            use_markdown=True,
        )
