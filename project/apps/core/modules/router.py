import logging
import typing

from libs.messengers.utils import escape_markdown

from ...common import interface
from ...common.exceptions import Shutdown
from ...common.routers.tplink import tplink_router
from ...core import constants, events
from ..base import BaseModule
from ..utils.wifi import check_if_host_is_at_home


__all__ = ('Router',)


@interface.module(
    title='Router',
    description='The module provides an integration with a router.',
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
            constants.USER_IS_AT_HOME: host_is_at_home,
        }

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            self.state.subscribe_toggle(
                constants.USER_IS_CONNECTED_TO_ROUTER,
                {
                    (
                        False,
                        True,
                    ): lambda name: events.user_is_connected_to_router.send(),
                    (
                        True,
                        False,
                    ): lambda name: events.user_is_disconnected_to_router.send(),
                },
            ),
            self.state.subscribe_toggle(
                constants.USER_IS_AT_HOME,
                {
                    (
                        False,
                        True,
                    ): lambda name: events.user_is_at_home.send(),
                    (
                        True,
                        False,
                    ): lambda name: events.user_is_not_at_home.send(),
                },
            ),
        )

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
