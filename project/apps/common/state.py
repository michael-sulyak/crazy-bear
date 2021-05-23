import threading
import typing
from collections import defaultdict

from .utils import synchronized


class StateException(Exception):
    pass


class State:
    _state: dict
    _lock: threading.RLock
    _subscribers_map: typing.Dict[str, typing.Tuple[typing.Callable, ...]]

    def __init__(self, init_state: typing.Optional[dict] = None) -> None:
        if init_state is None:
            init_state = {}

        self._lock = threading.RLock()
        self._state = init_state
        self._subscribers_map = defaultdict(tuple)

    def __getitem__(self, name: str) -> typing.Any:
        return self.get(name)

    def __setitem__(self, name: str, value: typing.Any) -> None:
        self.set(name=name, value=value)

    def __delitem__(self, name: str) -> None:
        self.remove(name)

    @synchronized
    def create(self, name: str, value: typing.Any = None) -> None:
        if self.has(name):
            raise StateException(f'The state already has key "{name}".')

        self.set(name, value, _need_to_create=True)

    def create_many(self, **kwargs) -> None:
        for name, value in kwargs.items():
            self.create(name, value)

    @synchronized
    def get(self, name: str) -> typing.Any:
        return self._state[name]

    def get_many(self, *names) -> tuple:
        return tuple(self.get(name) for name in names)

    def set(self, name: str, value: typing.Any, *, _need_to_create: bool = False) -> None:
        with self._lock:
            if not _need_to_create and not self.has(name):
                raise StateException(f'The state has not key "{name}".')

            old_value = self._state.get(name)
            self._state[name] = value

        if id(old_value) != id(value) or _need_to_create:
            self._notify(name=name, old_value=old_value, new_value=value)

    def set_many(self, **kwargs) -> None:
        for name, value in kwargs.items():
            self.set(name, value)

    @synchronized
    def has(self, name: str) -> bool:
        return name in self._state

    def has_many(self, *names) -> tuple:
        return tuple(self.has(name) for name in names)

    @synchronized
    def remove(self, name: str) -> None:
        if not self.has(name):
            raise StateException(f'The state has not key "{name}".')

        self._state.pop(name)

    @synchronized
    def subscribe(self, name: str, subscriber: typing.Callable) -> None:
        if not self.has(name):
            raise StateException(f'The state has not key "{name}".')

        self._subscribers_map[name] = (*self._subscribers_map[name], subscriber,)

    @synchronized
    def unsubscribe(self, name: str, subscriber: typing.Callable) -> None:
        self._subscribers_map[name] = tuple(
            subscriber_
            for subscriber_ in self._subscribers_map[name]
            if subscriber_ != subscriber
        )

    def _notify(self, *, name: str, old_value: typing.Any, new_value: typing.Any) -> None:
        with self._lock:
            subscribers = self._subscribers_map[name]

        for subscriber in subscribers:
            subscriber(name=name, old_value=old_value, new_value=new_value)
