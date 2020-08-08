import datetime
import queue

from .. import constants
from ..constants import AUTO_SECURITY_IS_ENABLED
from ...common.constants import AUTO, OFF, ON
from ...common.models import Signal
from ...common.utils import send_plot, user_is_connected_to_router
from ...guard.constants import SECURITY_IS_ENABLED
from ...messengers.base import BaseBotCommandHandler, Command, Message


__all__ = (
    'AutoSecurity',
)

from ...messengers.constants import MESSAGE_QUEUE


class AutoSecurity(BaseBotCommandHandler):
    support_commands = {
        constants.BotCommands.SECURITY,
        constants.BotCommands.STATS,
    }
    _last_clear_at: datetime

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()
        self._last_clear_at = now

    def init_state(self) -> None:
        self.state.create_many(**{
            AUTO_SECURITY_IS_ENABLED: False,
        })

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.SECURITY and command.first_arg == AUTO:
            if command.second_arg == ON:
                self._enable_auto_security()
            elif command.second_arg == OFF:
                self._disable_auto_security()
        elif command.name == constants.BotCommands.STATS:
            self._show_stats(command)

    def update(self) -> None:
        if not self.state[AUTO_SECURITY_IS_ENABLED]:
            return

        updates: queue.Queue = self.state[MESSAGE_QUEUE]
        user_is_connected = user_is_connected_to_router()

        if user_is_connected and self.state[SECURITY_IS_ENABLED]:
            self.messenger.send_message('The owner is found')
            updates.put(Message(command=Command(name=constants.BotCommands.SECURITY, args=(OFF,))))

        if not user_is_connected and not self.state[SECURITY_IS_ENABLED]:
            self.messenger.send_message('The owner is not found')
            updates.put(Message(command=Command(name=constants.BotCommands.SECURITY, args=(ON,))))

        Signal.add(signal_type=constants.USER_IS_CONNECTED_TO_ROUTER, value=int(user_is_connected))

        now = datetime.datetime.now()

        if now - self._last_clear_at >= datetime.timedelta(hours=24):
            Signal.clear(signal_type=constants.CPU_TEMPERATURE)
            self._last_clear_at = now

    def clear(self) -> None:
        self._disable_auto_security()

    def _enable_auto_security(self):
        self.state[AUTO_SECURITY_IS_ENABLED] = True

        self.messenger.send_message('Auto security is enabled')

        if user_is_connected_to_router() and not self.state[SECURITY_IS_ENABLED]:
            self.messenger.send_message('The owner is found')

    def _disable_auto_security(self):
        self.state[AUTO_SECURITY_IS_ENABLED] = False

        self.messenger.send_message('Auto security is disabled')

    def _show_stats(self, command: Command) -> None:
        stats = Signal.get_avg(
            signal_type=constants.USER_IS_CONNECTED_TO_ROUTER,
            delta_type=command.get_second_arg('hours'),
            delta_value=int(command.get_first_arg(24)),
        )

        if stats:
            send_plot(messenger=self.messenger, stats=stats, title='User is connected to router', attr='value')
