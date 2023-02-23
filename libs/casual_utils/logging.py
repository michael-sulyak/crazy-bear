import functools
import typing
from contextlib import contextmanager

import sentry_sdk


@contextmanager
def log_performance(operation_type: str, name: str) -> typing.Generator:
    with sentry_sdk.start_transaction(op=operation_type, name=name):
        yield


def log_func_performance(operation_type: str) -> typing.Callable:
    def decorate(func: typing.Callable) -> typing.Callable:
        func_name = f'{func.__module__}.{func.__qualname__}'

        @functools.wraps(func)
        def wrap_func(*args, **kwargs) -> typing.Any:
            with log_performance(operation_type, func_name):
                return func(*args, **kwargs)

        return wrap_func

    return decorate
