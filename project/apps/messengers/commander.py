import logging
import queue
import time
import typing

import schedule

from .base import BaseCommandHandler, BaseMessenger, Command, Message
from ..common.state import State
from ..common.threads import ThreadPool


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseCommandHandler, ...]
    scheduler: typing.Optional[schedule.Scheduler]
    message_queue: queue
    thread_pool: ThreadPool

    def __init__(self, *,
                 messenger: BaseMessenger,
                 command_handler_classes: typing.Iterable[typing.Type[BaseCommandHandler]],
                 state: State,
                 scheduler: schedule.Scheduler) -> None:
        self.message_queue = queue.Queue()
        self.thread_pool = ThreadPool()
        self.messenger = messenger
        self.state = state
        self.command_handlers = tuple(map(
            lambda command: command(
                messenger=messenger,
                state=state,
                message_queue=self.message_queue,
                scheduler=scheduler,
                thread_pool=self.thread_pool,
            ),
            command_handler_classes,
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
            time.sleep(1)
            return

        for command_handler in self.command_handlers:
            try:
                command_handler.update()
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                self.messenger.exception(e)
                logging.exception(e)

        self.thread_pool.part_sync()

        time.sleep(1)

    def process_updates(self) -> None:
        for messenger_update in self.messenger.get_updates():
            self.message_queue.put(messenger_update)

        while not self.message_queue.empty():
            self.messenger.start_typing()
            update: Message = self.message_queue.get()

            if update.command:
                self.process_command(update.command)

    def process_command(self, command: Command) -> None:
        is_processed = False

        for handler in self.command_handlers:
            if command.name not in handler.support_commands:
                continue

            try:
                handler.process_command(command)
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                logging.exception(e)
                self.messenger.exception(e)

            is_processed = True

        if not is_processed:
            self.messenger.send_message('Unknown command')

    def _close(self) -> None:
        logging.info('Home assistant is stopping...')
        schedule.clear()

        for command_handler in self.command_handlers:
            command_handler.clear()

        self.thread_pool.sync()

        self.messenger.send_message('Goodbye!')
