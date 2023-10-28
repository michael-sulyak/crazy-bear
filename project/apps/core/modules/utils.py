import datetime
import typing

from libs.messengers.utils import escape_markdown
from libs.task_queue import TaskPriorities
from ..base import BaseModule, Command
from ..constants import (
    BotCommands,
)
from ...common import doc


__all__ = (
    'Utils',
)


@doc.doc(
    title='Utils',
    description=(
        'The module provides additional utils.'
    ),
    commands=(
        doc.Command(
            BotCommands.TIMER,
            doc.Value('number', type='int'),
            doc.Value('time_type'),
            '|',
            doc.Value('command'),
        ),
    ),
)
class Utils(BaseModule):
    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.TIMER:
            number = int(command.first_arg)
            time_type = command.second_arg

            delta = datetime.timedelta(**{time_type: number})
            command_name_for_run, *command_args_for_run = command.args[command.args.index('|') + 1:]
            command_for_run = Command(name=command_name_for_run, args=command_args_for_run)

            self.task_queue.put(
                lambda: (
                    self.messenger.send_message(
                        f'Run scheduled command `{escape_markdown(str(command_for_run))}`',
                        use_markdown=True,
                    ),
                    self._run_command(command_for_run.name, *command_for_run.args),
                ),
                run_after=datetime.datetime.now() + delta,
                priority=TaskPriorities.LOW,
            )

            self.messenger.send_message(
                f'`{escape_markdown(str(command_for_run))}` is sent',
                use_markdown=True,
            )

            return True

        return False
