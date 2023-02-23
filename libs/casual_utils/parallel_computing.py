import functools
import threading
import typing


def synchronized_method(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def _wrapper(self, *args, **kwargs) -> typing.Any:
        try:
            lock = self._lock
        except AttributeError as e:
            raise Exception(f'"{func.__name__}" doesn\'t contain "_lock".') from e

        with lock:
            return func(self, *args, **kwargs)

    return _wrapper


def single_synchronized(func: typing.Callable) -> typing.Callable:
    lock = threading.RLock()

    @functools.wraps(func)
    def _wrapper(*args, **kwargs) -> typing.Any:
        with lock:
            return func(*args, **kwargs)

    return _wrapper
