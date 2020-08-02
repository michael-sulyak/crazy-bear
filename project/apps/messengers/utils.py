import queue
import typing

from .base import Command, Message
from .constants import MESSAGE_QUEUE
from ..common.state import State


def scheduled_task(state: State, command_name: str) -> typing.Callable:
    def _task():
        updates: queue.Queue = state[MESSAGE_QUEUE]
        updates.put(Message(command=Command(name=command_name)))

    return _task
