import datetime

from libs.messengers.utils import escape_markdown
from libs.task_queue import IntervalTask, TaskPriorities

from .... import config
from ...common import interface
from ..base import BaseModule


__all__ = ('ZigBeeController',)


@interface.module(
    title='ZigBee',
    description='The module manages ZigBee devices.',
)
class ZigBeeController(BaseModule):
    _previous_availability_map: dict[str, bool]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._previous_availability_map = {}

    def init_repeatable_tasks(self) -> tuple:
        run_after = datetime.datetime.now() + datetime.timedelta(minutes=10)

        return (
            IntervalTask(
                target=lambda: self._check_connected_devices(check_active_devices=True),
                priority=TaskPriorities.LOW,
                interval=config.ZIGBEE_AVAILABILITY_ACTIVE_TIMEOUT_CHECK,
                run_after=run_after,
            ),
            IntervalTask(
                target=lambda: self._check_connected_devices(check_active_devices=False),
                priority=TaskPriorities.LOW,
                interval=config.ZIGBEE_AVAILABILITY_PASSIVE_TIMEOUT_CHECK,
                run_after=run_after,
            ),
        )

    @interface.command('/zigbee_status')
    def _show_status(self) -> None:
        self.messenger.send_message(f'Is health: `{self.context.zig_bee.is_health()}`', use_markdown=True)

        devices_info = '\n\n'.join(device.to_str() for device in self.context.zig_bee.devices)

        self.messenger.send_message(f'*Devices*\n\n{devices_info}', use_markdown=True)

        temporary_subscribers = '\n'.join(self.context.zig_bee.temporary_subscribers_map.keys())
        self.messenger.send_message(
            f'Temporary subscribers:\n```\n{temporary_subscribers or "-"}\n```',
            use_markdown=True,
        )

        permanent_subscribers = '\n'.join(self.context.zig_bee.permanent_subscribers_map.keys())
        self.messenger.send_message(
            f'Permanent subscribers:\n```\n{permanent_subscribers or "-"}\n```',
            use_markdown=True,
        )

        self.messenger.send_message(
            f'Availability map:\n```\n{self.context.zig_bee.availability_map or "-"}\n```',
            use_markdown=True,
        )

    def _check_connected_devices(self, *, check_active_devices: bool) -> None:
        zig_bee = self.context.zig_bee

        for device in zig_bee.devices:
            if device.is_coordinator:
                continue

            if device.is_active != check_active_devices:
                continue

            if device.is_available:
                if not self._previous_availability_map.get(device.friendly_name, True):
                    self.messenger.send_message(
                        f'ZigBee device *{escape_markdown(device.friendly_name)}* is available now',
                        use_markdown=True,
                    )
            elif device.is_available is None:
                self.messenger.send_message(
                    f'ZigBee device *{escape_markdown(device.friendly_name)}* has unknown availability',
                    use_markdown=True,
                )
            else:
                self.messenger.send_message(
                    f'ZigBee device *{escape_markdown(device.friendly_name)}* is not available',
                    use_markdown=True,
                )

            self._previous_availability_map[device.friendly_name] = device.is_available
