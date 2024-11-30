import logging
import queue
import typing

from telegram.error import NetworkError

from libs.casual_utils.logging import log_performance
from libs.smart_devices.base import BaseSmartDevice
from libs.messengers.base import BaseMessenger
from libs.task_queue import BaseTaskQueue, BaseWorker, MemTaskQueue, ThreadWorker
from libs.task_queue.middlewares import ConcreteRetries, ExceptionLogging, SupportOfRetries
from libs.zigbee.base import ZigBee
from . import events, events as core_events
from .base import BaseModule, ModuleContext
from .events import new_message
from ..common.base import BaseReceiver
from ..common.exceptions import Shutdown
from ..common.state import State
from ..db import close_db_session


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: tuple[BaseModule, ...]
    message_queue: queue.Queue
    task_queue: BaseTaskQueue
    task_worker: BaseWorker
    zig_bee: ZigBee
    _receivers: tuple[BaseReceiver, ...]

    def __init__(
        self,
        *,
        messenger: BaseMessenger,
        module_classes: tuple[typing.Type[BaseModule], ...],
        state: State,
        zig_bee: ZigBee,
        smart_devices: tuple[BaseSmartDevice, ...],
    ) -> None:
        self.message_queue = queue.Queue()
        self.task_queue = MemTaskQueue()
        self.task_worker = ThreadWorker(
            task_queue=self.task_queue,
            middlewares=(
                ExceptionLogging(),
                ConcreteRetries(
                    exceptions=(
                        ConnectionError,
                        NetworkError,
                    )
                ),
                SupportOfRetries(),
            ),
            count=2,
            on_close=close_db_session,
        )
        self.messenger = messenger
        self.state = state
        self.zig_bee = zig_bee

        smart_devices_map = {}

        for smart_device in smart_devices:
            if smart_device.friendly_name in smart_devices_map:
                raise RuntimeError(f'"{smart_device.friendly_name}" has been already added in the map.')

            smart_devices_map[smart_device.friendly_name] = smart_device

        module_context = ModuleContext(
            messenger=self.messenger,
            state=self.state,
            task_queue=self.task_queue,
            zig_bee=self.zig_bee,
            smart_devices_map=smart_devices_map,
        )

        self.command_handlers = tuple(module_class(context=module_context) for module_class in module_classes)

        self._receivers = (new_message.connect(lambda message: self.message_queue.put(message)),)

    def run(self) -> None:
        self.zig_bee.open()
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
        message = self.message_queue.get(block=True)

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

        logging.info('[shutdown] Closing ZigBee...')
        self.zig_bee.close()

        self.messenger.send_message('Goodbye!')
