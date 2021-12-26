import logging
import queue
import typing

from . import events as core_events
from .base import BaseModule, ModuleContext
from ..common.events import Receiver
from ..common.exceptions import Shutdown
from ..common.state import State
from ..common.utils import log_performance
from ..db import close_db_session
from ..messengers import events
from ..messengers.base import BaseMessenger
from ..messengers.events import new_message
from ..task_queue import BaseTaskQueue, BaseWorker, MemTaskQueue, ThreadWorker


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseModule, ...]
    message_queue: queue.Queue
    task_queue: BaseTaskQueue
    task_worker: BaseWorker
    _receivers: typing.Tuple[Receiver, ...]

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

        self._receivers = (
            new_message.connect(lambda message: self.message_queue.put(message)),
        )

    def run(self) -> typing.NoReturn:
        self.task_worker.run()

        logging.info('Commander is started.')

        while True:
            try:
                self.process_updates()
            except Shutdown:
                break
            except Exception as e:
                logging.exception(e)
                self.messenger.exception(e)

        self.close()

    def process_updates(self) -> None:
        message = self.message_queue.get()

        if not message.command:
            return

        logging.info(
            'Command: %s args=%s kwargs=%s',
            message.command.name,
            message.command.args,
            message.command.kwargs,
        )

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

        logging.info('[shutdown] Disconnecting receivers...')
        for receiver in self._receivers:
            receiver.disconnect()

        self.messenger.send_message('Goodbye!')
