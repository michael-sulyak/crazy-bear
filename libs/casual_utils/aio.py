import asyncio
import functools
import threading
import typing


# TODO: Close loops
_thread_event_loops: dict = {}
_lock = threading.RLock()


def async_to_sync(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _lock:
            thread_id = threading.get_ident()
            if thread_id not in _thread_event_loops:
                _thread_event_loops[thread_id] = asyncio.new_event_loop()

            loop = _thread_event_loops[thread_id]

        return loop.run_until_complete(func(*args, **kwargs))

    return wrapper
