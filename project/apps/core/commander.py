import logging
import queue
import time
import typing

from . import events as core_events
from .base import BaseModule, ModuleContext
from ..common.exceptions import Shutdown
from ..common.state import State
from ..common.utils import is_sleep_hours, log_performance
from ..db import close_db_session
from ..messengers import events
from ..messengers.base import BaseMessenger
from ..task_queue import BaseTaskQueue, BaseWorker, MemTaskQueue, ThreadWorker


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseModule, ...]
    message_queue: queue.Queue
    task_queue: BaseTaskQueue
    task_worker: BaseWorker

    def __init__(self, *,
                 messenger: BaseMessenger,
                 module_classes: typing.Iterable[typing.Type[BaseModule]],
                 state: State) -> None:
        self.message_queue = queue.Queue()
        self.task_queue = MemTaskQueue()
        self.task_worker = ThreadWorker(task_queue=self.task_queue, on_close=close_db_session)
        self.messenger = messenger
        self.state = state

        module_context = ModuleContext(
            messenger=self.messenger,
            state=self.state,
            task_queue=self.task_queue,
        )

        self.command_handlers = tuple(
            module_class(context=module_context)
            for module_class in module_classes
        )

    def run(self) -> typing.NoReturn:
        self.task_worker.run()

        logging.info('Commander is started.')

        while True:
            try:
                self.tick()

                if is_sleep_hours():
                    time.sleep(1)
                else:
                    time.sleep(0.1)
            except Shutdown:
                break

        self.close()

    def tick(self) -> None:
        try:
            self.process_updates()
        except Shutdown:
            raise
        except Exception as e:
            logging.exception(e)
            self.messenger.exception(e)

    def process_updates(self) -> None:
        for message in self.messenger.get_updates():
            if message.command:
                logging.info(
                    'Command: %s args=%s kwargs=%s',
                    message.command.name,
                    message.command.args,
                    message.command.kwargs,
                )

            self.message_queue.put(message)

        while True:
            try:
                message = self.message_queue.get(block=False)
            except queue.Empty:
                break

            if not message.command:
                continue

            with log_performance('cmd', str(message.command)):
                results, exceptions = events.input_command.process(command=message.command)
                is_processed = exceptions or any(map(lambda x: x is True, results))

                for exception in exceptions:
                    self.messenger.exception(exception)

                if not is_processed and not exceptions:
                    self.messenger.send_message('Unknown command')

    def close(self) -> None:
        logging.info('Home assistant is stopping...')

        logging.info('[shutdown] Closing task queue...')
        self.task_worker.stop()

        logging.info('[shutdown] Sending "shutdown" signal...')
        core_events.shutdown.send()

        logging.info('[shutdown] Closing messenger...')
        self.messenger.close()

        self.messenger.send_message('Goodbye!')
