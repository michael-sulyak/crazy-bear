import logging
import typing

from libs.messengers.utils import escape_markdown
from ..base import BaseModule, Command
from ...common import interface
from ...common.exceptions import Shutdown
from ...common.routers.mi import mi_wifi
from ...core import constants, events
from ...devices.utils import check_if_host_is_at_home


__all__ = (
    'Router',
)


@interface.module(
    title='Router',
    description=(
        'The module provides an integration with a router.'
    ),
    use_auto_mapping_for_commands=True,
)
class Router(BaseModule):
    @property
    def initial_state(self) -> dict[str, typing.Any]:
        host_is_at_home = False

        try:
            host_is_at_home = check_if_host_is_at_home()
        except Shutdown:
            raise
        except Exception as e:
            logging.exception(e)

        return {
            constants.USER_IS_CONNECTED_TO_ROUTER: host_is_at_home,
        }

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self.state.subscribe_toggle(constants.USER_IS_CONNECTED_TO_ROUTER, {
                (False, True,): lambda name: events.user_is_connected_to_router.send(),
                (True, False,): lambda name: events.user_is_disconnected_to_router.send(),
                (None, True,): lambda name: events.user_is_connected_to_router.send(),
            }),
        )

    @interface.command(constants.BotCommands.RAW_WIFI_DEVICES)
    def _show_wifi_connected_devices(self, command: Command) -> None:
        message = ''

        for device in mi_wifi.device_list()['list']:
            for key, value in device.items():
                message += f'*{escape_markdown(str(key))}:* {escape_markdown(str(value))}\n'

            message += '\n'

        self.messenger.send_message(message, use_markdown=True)
