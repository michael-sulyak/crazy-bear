import asyncio
import functools
import typing


loop = asyncio.get_event_loop()


def async_to_sync(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop).result()

    return wrapper
