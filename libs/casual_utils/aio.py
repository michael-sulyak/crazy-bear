import asyncio
import functools
import logging
import threading
import typing


class AsyncThread:
    _lock: threading.Lock()
    _loop: asyncio.AbstractEventLoop
    _thread: threading.Thread | None = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._create_loop()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop.is_closed():
            logging.error('Thread for asyncio was closed')
            raise RuntimeError('Event loop is closed')

        return self._loop

    def close_loop(self) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop())

        self._thread.join()

    def _create_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._start_background_loop,
            daemon=True,
        )
        self._thread.start()

    def _start_background_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()


async_thread = AsyncThread()


def async_to_sync(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        loop = async_thread.get_loop()
        task = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop)
        return task.result()

    return wrapper
