import datetime
import typing

from ..base import BaseModule, Command
from ..constants import (
    BotCommands,
)
from ...common import doc
from ...task_queue import TaskPriorities


__all__ = (
    'ExtraCommands',
)


class ExtraCommands(BaseModule):
    doc = doc.generate_doc(
        title='ExtraCommands',
        commands=(
            doc.CommandDef(
                BotCommands.TIMER,
                doc.VarDef('number', type='int'),
                doc.VarDef('time_type'),
                '|',
                doc.VarDef('command'),
            ),
        ),
    )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.TIMER:
            number = int(command.first_arg)
            time_type = command.second_arg

            delta = datetime.timedelta(**{time_type: number})
            command_name_for_run, *command_args_for_run = command.args[command.args.index('|') + 1:]
            command_for_run = Command(name=command_name_for_run, args=command_args_for_run)

            self.task_queue.put(
                lambda: (
                    self.messenger.send_message(f'Run scheduled command {command_for_run}'),
                    self._run_command(command_for_run.name, *command_for_run.args),
                ),
                run_after=datetime.datetime.now() + delta,
                priority=TaskPriorities.LOW,
            )

            self.messenger.send_message(f'{command_for_run} is sent')

            return True

        return False
