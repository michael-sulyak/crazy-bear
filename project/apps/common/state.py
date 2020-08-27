import threading
import typing


class StateException(Exception):
    pass


class State:
    _state: dict
    lock: threading.RLock

    def __init__(self, init_state: typing.Optional[dict] = None) -> None:
        if init_state is None:
            init_state = {}

        self.lock = threading.RLock()
        self._state = init_state

    def __getitem__(self, name: str) -> typing.Any:
        return self.get(name)

    def __setitem__(self, name: str, value: typing.Any) -> None:
        self.set(name=name, value=value)

    def __delitem__(self, name: str) -> None:
        self.remove(name)

    def create(self, name: str, value: typing.Any = None) -> None:
        with self.lock:
            if self.has(name):
                raise StateException(f'The state already has key "{name}".')

            self.set(name, value, _check_key=False)

    def create_many(self, **kwargs) -> None:
        with self.lock:
            for name, value in kwargs.items():
                self.create(name, value)

    def get(self, name: str) -> typing.Any:
        with self.lock:
            return self._state[name]

    def get_many(self, *names) -> tuple:
        with self.lock:
            return tuple(self.get(name) for name in names)

    def set(self, name: str, value: typing.Any, *, _check_key: bool = True) -> None:
        with self.lock:
            if _check_key and not self.has(name):
                raise StateException(f'The state has not key "{name}".')

            self._state[name] = value

    def set_many(self, **kwargs) -> None:
        with self.lock:
            for name, value in kwargs.items():
                self.set(name, value)

    def has(self, name: str) -> bool:
        with self.lock:
            return name in self._state

    def has_many(self, *names) -> tuple:
        with self.lock:
            return tuple(self.has(name) for name in names)

    def remove(self, name: str) -> None:
        with self.lock:
            self._state.pop(name)
