import queue
import typing

from .base import Command, Message


def scheduled_task(message_queue: queue, command_name: str) -> typing.Callable:
    def _task():
        message_queue.put(Message(command=Command(name=command_name)))

    return _task
