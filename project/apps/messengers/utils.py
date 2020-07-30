import queue
import typing

from .base import MessengerCommand, MessengerUpdate
from .constants import UPDATES
from ..common.state import State


def scheduled_task(state: State, command_name: str) -> typing.Callable:
    def _task():
        updates: queue.Queue = state[UPDATES]
        updates.put(MessengerUpdate(command=MessengerCommand(name=command_name)))

    return _task
