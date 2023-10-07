import contextlib
import threading
import typing
from dataclasses import dataclass

from libs.casual_utils.parallel_computing import synchronized_method
from .base import BaseReceiver


class StateException(Exception):
    pass


class State:
    _state: dict
    _lock: threading.RLock
    _subscribers_map: typing.Dict[str, typing.Set[typing.Callable]]
    _subscriber_locks_map: typing.Dict[str, threading.RLock]

    def __init__(self, init_state: typing.Optional[dict] = None) -> None:
        self._lock = threading.RLock()
        self._state = {}
        self._subscribers_map = {}
        self._subscriber_locks_map = {}

        if init_state:
            self.create_many(**init_state)

    def __getitem__(self, name: str) -> typing.Any:
        return self.get(name)

    def __setitem__(self, name: str, value: typing.Any) -> None:
        self.set(name=name, value=value)

    def __delitem__(self, name: str) -> None:
        self.remove(name)

    @synchronized_method
    def create(self, name: str, value: typing.Any = None) -> None:
        if self.has(name):
            raise StateException(f'The state already has key "{name}".')

        self._subscribers_map[name] = set()
        self._subscriber_locks_map[name] = threading.RLock()
        self.set(name, value, _need_to_create=True)

    @synchronized_method
    def create_many(self, **kwargs) -> None:
        for name, value in kwargs.items():
            self.create(name, value)

    @synchronized_method
    def get(self, name: str) -> typing.Any:
        return self._state[name]

    @synchronized_method
    def get_many(self, *names) -> tuple:
        return tuple(self.get(name) for name in names)

    def set(self, name: str, value: typing.Any, *, _need_to_create: bool = False) -> None:
        with self._lock:
            if not _need_to_create and not self.has(name):
                raise StateException(f'The state has not key "{name}".')

            old_value = self._state.get(name)
            self._state[name] = value
            subscriber_lock = self._subscriber_locks_map[name]

        if id(old_value) != id(value) or _need_to_create:
            with subscriber_lock:
                self._notify(name=name, old_value=old_value, new_value=value)

    def set_many(self, **kwargs) -> None:
        for name, value in kwargs.items():
            self.set(name, value)

    @synchronized_method
    def has(self, name: str) -> bool:
        return name in self._state

    def has_many(self, *names) -> tuple:
        return tuple(self.has(name) for name in names)

    @synchronized_method
    def remove(self, name: str) -> None:
        if not self.has(name):
            raise StateException(f'The state has not key "{name}".')

        self._state.pop(name)
        self._subscribers_map.pop(name)
        self._subscriber_locks_map.pop(name)

    def subscribe(self, name: str, subscriber: typing.Callable) -> 'Subscriber':
        with self._lock:
            if not self.has(name):
                raise StateException(f'The state has not key "{name}".')

            with self._subscriber_locks_map[name]:
                self._subscribers_map[name].add(subscriber)

        return Subscriber(
            state=self,
            name=name,
            func=subscriber,
        )

    def subscribe_toggle(
            self,
            name: str,
            methods_map: typing.Dict[tuple[typing.Any, typing.Any], typing.Callable],
    ) -> 'Subscriber':
        def _subscriber(*, name: str, old_value: typing.Any, new_value: typing.Any):
            methods_map[(old_value, new_value,)](name=name)

        return self.subscribe(name, _subscriber)

    @synchronized_method
    def unsubscribe(self, name: str, subscriber: typing.Callable) -> None:
        if not self.has(name):
            raise StateException(f'The state has not key "{name}".')

        try:
            self._subscribers_map[name].remove(subscriber)
        except KeyError:
            pass

    @contextlib.contextmanager
    def lock(self, name: str) -> typing.Generator[None, None, None]:
        with self._lock:
            if not self.has(name):
                raise StateException(f'The state has not key "{name}".')

            lock = self._subscriber_locks_map[name]

        with lock:
            yield

    def _notify(self, *, name: str, old_value: typing.Any, new_value: typing.Any) -> None:
        for subscriber in self._subscribers_map[name]:
            subscriber(name=name, old_value=old_value, new_value=new_value)


@dataclass
class Subscriber(BaseReceiver):
    state: State
    name: str
    func: typing.Callable

    def disconnect(self) -> None:
        self.state.unsubscribe(self.name, self.func)
