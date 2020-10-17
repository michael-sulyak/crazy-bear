import logging
import queue
import time
import typing

import schedule

from . import events as core_events
from .base import BaseModule, CommandHandlerContext, Message
from ..common.state import State
from ..common.threads import TaskQueue
from ..db import close_db_session
from ..messengers import events
from ..messengers.base import BaseMessenger


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseModule, ...]
    scheduler: typing.Optional[schedule.Scheduler]
    message_queue: queue
    task_queue: TaskQueue

    def __init__(self, *,
                 messenger: BaseMessenger,
                 module_classes: typing.Iterable[typing.Type[BaseModule]],
                 state: State,
                 scheduler: schedule.Scheduler) -> None:
        self.message_queue = queue.Queue()
        self.task_queue = TaskQueue(on_close=close_db_session)
        self.messenger = messenger
        self.state = state

        command_handler_context = CommandHandlerContext(
            messenger=messenger,
            state=state,
            message_queue=self.message_queue,
            scheduler=scheduler,
            task_queue=self.task_queue,
        )

        self.command_handlers = tuple(map(
            lambda command: command(context=command_handler_context),
            module_classes,
        ))
        self.scheduler = scheduler

    def run(self) -> typing.NoReturn:
        while True:
            try:
                self.tick()
            except KeyboardInterrupt:
                break

        self._close()

        exit(0)

    def tick(self) -> None:
        if self.scheduler:
            try:
                self.scheduler.run_pending()
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                self.messenger.exception(e)
                logging.exception(e)

        try:
            self.process_updates()
        except KeyboardInterrupt as e:
            raise e
        except Exception as e:
            logging.exception(e)
            return

        core_events.tick.send()

        time.sleep(1)

    def process_updates(self) -> None:
        for message in self.messenger.get_updates():
            if message.command:
                logging.info(
                    f'Command: {message.command.name} args={message.command.args} kwargs={message.command.kwargs}',
                )

            self.message_queue.put(message)

        while not self.message_queue.empty():
            self.messenger.start_typing()
            update: Message = self.message_queue.get()

            if update.command:
                results, exceptions = events.input_command.process(command=update.command)
                is_processed = exceptions or any(map(lambda x: x is True, results))

                for exception in exceptions:
                    self.messenger.exception(exception)

                if not is_processed:
                    self.messenger.send_message('Unknown command')

    def _close(self) -> None:
        logging.info('Home assistant is stopping...')

        core_events.shutdown.send()
        schedule.clear()
        self.task_queue.close()

        self.messenger.send_message('Goodbye!')
