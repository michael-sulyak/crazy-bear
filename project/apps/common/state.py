import typing


class DEFAULT:
    pass


class StateException(Exception):
    pass


class State:
    _state: dict

    def __init__(self, init_state: typing.Optional[dict] = None) -> None:
        if init_state is None:
            init_state = {}

        self._state = init_state

    def create(self, name: str, value: typing.Any = None) -> None:
        if self.has(name):
            raise StateException(f'The state already has key "{name}".')

        self.set(name, value, _check_key=False)

    def create_many(self, *args, **kwargs) -> None:
        if args and kwargs:
            raise StateException('Use args or kwargs.')

        if kwargs:
            fields = kwargs
        elif len(args) == 1 and hasattr(args[0], 'items'):
            fields = args[0]
        else:
            raise StateException('Invalid arguments.')

        for name, value in fields.items():
            self.create(name, value)

    def get(self, name: str) -> typing.Any:
        return self._state[name]

    def get_many(self, *names) -> typing.Iterator:
        return (self.get(name) for name in names)

    def set(self, name: str, value: typing.Any, _check_key: bool = True) -> None:
        if _check_key and not self.has(name):
            raise StateException(f'The state has not key "{name}".')

        self._state[name] = value

    def set_default(self, name: str, value: typing.Any) -> None:
        if not self.has(name):
            self.create(name, value)

    def clear(self, name: str) -> None:
        self.set(name, None)

    def set_true(self, name: str) -> None:
        self.set(name, True)

    def set_false(self, name: str) -> None:
        self.set(name, False)

    def set_many(self, **kwargs) -> None:
        for name, value in kwargs.items():
            self.set(name, value)

    def has(self, name: str) -> bool:
        return name in self._state

    def has_many(self, *names) -> typing.Iterator:
        return (self.has(name) for name in names)

    def remove(self, name: str) -> None:
        self._state.pop(name)
