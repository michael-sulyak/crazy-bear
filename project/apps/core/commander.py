import datetime
import logging
import queue
import time
import typing

import schedule

from . import events as core_events
from .base import BaseModule, ModuleContext, Message
from ..common.exceptions import Shutdown
from ..common.state import State
from ..common.utils import is_sleep_hours
from ..task_queue import BaseTaskQueue, BaseWorker, MemTaskQueue, ThreadWorker
from ..db import close_db_session
from ..messengers import events
from ..messengers.base import BaseMessenger


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseModule, ...]
    scheduler: schedule.Scheduler
    message_queue: queue
    task_queue: BaseTaskQueue
    task_worker: BaseWorker

    def __init__(self, *,
                 messenger: BaseMessenger,
                 module_classes: typing.Iterable[typing.Type[BaseModule]],
                 state: State,
                 scheduler: schedule.Scheduler) -> None:
        self.message_queue = queue.Queue()
        self.task_queue = MemTaskQueue()
        self.task_worker = ThreadWorker(task_queue=self.task_queue, on_close=close_db_session)
        self.task_worker.run()
        self.messenger = messenger
        self.state = state
        self.scheduler = scheduler

        module_context = ModuleContext(
            messenger=self.messenger,
            state=self.state,
            message_queue=self.message_queue,
            scheduler=self.scheduler,
            task_queue=self.task_queue,
        )

        self.command_handlers = tuple(
            module_class(context=module_context)
            for module_class in module_classes
        )

    def run(self) -> typing.NoReturn:
        while True:
            try:
                self.tick()

                if is_sleep_hours(datetime.datetime.now()):
                    time.sleep(1)
                else:
                    time.sleep(0.2)
            except Shutdown:
                break

        self.close()

    def tick(self) -> None:
        try:
            # All jobs have to be in async queue
            self.scheduler.run_pending()
        except Shutdown as e:
            raise e
        except Exception as e:
            self.messenger.exception(e)
            logging.exception(e)

        try:
            self.process_updates()
        except Shutdown as e:
            raise e
        except Exception as e:
            self.messenger.exception(e)
            logging.exception(e)

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

    def close(self) -> None:
        logging.info('Home assistant is stopping...')

        logging.info('[shutdown] Clearing schedule...')
        schedule.clear()

        logging.info('[shutdown] Closing task queue...')
        self.task_worker.stop()

        logging.info('[shutdown] Sending "shutdown" signal...')
        core_events.shutdown.send()

        self.messenger.send_message('Goodbye!')
