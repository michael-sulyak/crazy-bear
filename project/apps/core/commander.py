import logging
import queue

from telegram.error import NetworkError

from libs.casual_utils.logging import log_performance
from libs.messengers.base import BaseMessenger
from libs.smart_devices.base import BaseSmartDevice
from libs.task_queue import BaseTaskQueue, BaseWorker, MemTaskQueue, ThreadWorker
from libs.task_queue.middlewares import ConcreteRetries, ExceptionLogging, SupportOfRetries
from libs.zigbee.base import ZigBee

from ..common.base import BaseReceiver
from ..common.exceptions import Shutdown
from ..common.state import State
from ..db import close_db_session
from . import events
from . import events as core_events
from .base import BaseModule, ModuleContext
from .events import new_message


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
        module_classes: tuple[type[BaseModule], ...],
        state: State,
        zig_bee: ZigBee,
        smart_devices: tuple[BaseSmartDevice, ...],
    ) -> None:
        self._closed = False
        self.message_queue = queue.Queue()
        self.task_queue = MemTaskQueue()
        self.task_worker = ThreadWorker(
            task_queue=self.task_queue,
            middlewares=(
                ExceptionLogging(),
                SupportOfRetries(),
                ConcreteRetries(
                    exceptions=(
                        ConnectionError,
                        NetworkError,
                    ),
                ),
            ),
            count=2,
            on_close=close_db_session,
            on_task_done=close_db_session,
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
        try:
            self.zig_bee.open()
            self.task_worker.run()
            logging.info('Commander is started.')

            while True:
                try:
                    self.process_updates()
                except Shutdown:
                    raise
                except Exception as exc:
                    logging.exception('Cannot process command')
                    self._report_exception(exc)
                finally:
                    close_db_session()
        except Shutdown:
            logging.info('Commander received shutdown request.')
        finally:
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
                self._report_exception(exception)

            if not is_processed and not exceptions:
                self.messenger.send_message(
                    'Unknown command or invalid arguments. Use /help for commands or /start to restore navigation.',
                )

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        logging.info('Home assistant is stopping...')

        def disconnect_receivers() -> None:
            for receiver in self._receivers:
                receiver.disconnect()

        cleanup_steps = (
            ('task workers', self.task_worker.stop),
            ('modules', core_events.shutdown.send),
            ('receivers', disconnect_receivers),
            ('ZigBee', self.zig_bee.close),
            ('goodbye message', lambda: self.messenger.send_message('Goodbye!')),
            ('messenger', self.messenger.close),
        )

        for name, cleanup in cleanup_steps:
            try:
                logging.info('[shutdown] Closing %s...', name)
                cleanup()
            except Exception:
                logging.exception('[shutdown] Cannot close %s', name)

    def _report_exception(self, exception: Exception) -> None:
        try:
            self.messenger.exception(exception)
        except Exception:
            # Telegram being offline must not terminate command processing.
            logging.exception('Cannot report command failure to Telegram')
