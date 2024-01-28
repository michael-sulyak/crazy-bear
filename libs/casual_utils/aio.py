import asyncio
import functools
import logging
import threading
import typing


# TODO: Close loops
# _thread_event_loops: dict = {}
_lock = threading.Lock()

# def async_to_sync(func: typing.Callable) -> typing.Callable:
#     @functools.wraps(func)
#     def wrapper(*args, **kwargs):
#         with _lock:
#             thread_id = threading.get_ident()
#             if thread_id not in _thread_event_loops:
#                 _thread_event_loops[thread_id] = asyncio.new_event_loop()
#
#             loop = _thread_event_loops[thread_id]
#
#         return loop.run_until_complete(func(*args, **kwargs))
#
#     return wrapper

_loop = None


def _start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def async_to_sync(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global _loop

        if _loop is None:
            with _lock:
                if _loop is None:
                    _loop = asyncio.new_event_loop()
                    tread = threading.Thread(target=_start_background_loop, args=(_loop,), daemon=True)
                    tread.start()

            if _loop.is_closed():
                logging.error('Thread for asyncio was closed')

        task = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), _loop)
        return task.result()

    return wrapper
