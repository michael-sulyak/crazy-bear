import logging
import queue
import time
import typing

import schedule

from .base import BaseBotCommandHandler, BaseMessenger, Command, Message
from .constants import INITED_AT, THREAD_POOL, MESSAGE_QUEUE
from ..common.state import State
from ..common.threads import ThreadPool


class Commander:
    messenger: BaseMessenger
    state: State
    command_handlers: typing.Tuple[BaseBotCommandHandler, ...]
    scheduler: typing.Optional[schedule.Scheduler]

    def __init__(self, *,
                 messenger: BaseMessenger,
                 commands: typing.Iterable,
                 state: State,
                 scheduler: schedule.Scheduler) -> None:
        assert all(state.has_many(INITED_AT, MESSAGE_QUEUE, THREAD_POOL))

        self.messenger = messenger
        self.state = state
        self.command_handlers = tuple(map(lambda command: command(messenger=messenger, state=state), commands))
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
            self.scheduler.run_pending()

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

        thread_pool: ThreadPool = self.state[THREAD_POOL]
        thread_pool.part_sync()

        time.sleep(1)

    def process_updates(self) -> None:
        updates: queue.Queue = self.state[MESSAGE_QUEUE]

        for messenger_update in self.messenger.get_updates():
            updates.put(messenger_update)

        while not updates.empty():
            self.messenger.start_typing()
            update: Message = updates.get()

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

        thread_pool: ThreadPool = self.state[THREAD_POOL]
        thread_pool.sync()

        self.messenger.send_message('Goodbye!')
