import datetime

from libs.messengers.utils import escape_markdown
from libs.task_queue import TaskPriorities
from ..base import BaseModule, Command
from ..constants import (
    BotCommands,
)
from ...common import interface


__all__ = (
    'Utils',
)


@interface.module(
    title='Utils',
    description=(
        'The module provides additional utils.'
    ),
)
class Utils(BaseModule):
    @interface.command(
        BotCommands.TIMER,
        interface.Value('number', python_type=int),
        interface.Choices('seconds', 'minutes', 'hours', 'days'),
        '|',
        interface.Args('command'),
    )
    def _timer(self, command: Command) -> None:
        number = int(command.first_arg)
        time_type = command.second_arg

        delta = datetime.timedelta(**{time_type: number})
        command_name_for_run, *command_args_for_run = command.args[command.args.index('|') + 1:]
        command_for_run = Command(name=command_name_for_run, args=command_args_for_run)
        run_after = datetime.datetime.now() + delta

        self.task_queue.put(
            lambda: (
                self.messenger.send_message(
                    f'Run scheduled command `{escape_markdown(str(command_for_run))}`',
                    use_markdown=True,
                ),
                self._run_command(command_for_run.name, *command_for_run.args),
            ),
            run_after=run_after,
            priority=TaskPriorities.LOW,
        )

        self.messenger.send_message(
            f'`{escape_markdown(str(command_for_run))}` is sent\\.\nIt will be run at `{run_after}`\\.',
            use_markdown=True,
        )
