import collections
import datetime
import logging
import threading
import typing
from time import sleep

from .utils import synchronized


class ThreadPool:
    # TODO: Maybe remove (not used)
    _timedelta_for_part_sync: datetime.timedelta
    _threads: typing.Deque[typing.Tuple[threading.Thread, datetime.datetime]]
    _lock: threading.Lock

    def __init__(self, timedelta_for_part_sync: typing.Optional[datetime.timedelta] = None) -> None:
        if timedelta_for_part_sync is None:
            timedelta_for_part_sync = datetime.timedelta(seconds=20)

        self._timedelta_for_part_sync = timedelta_for_part_sync
        self._threads = collections.deque()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._threads)

    @synchronized
    def run(self,
            target: typing.Callable,
            args: tuple = None,
            kwargs: typing.Dict[str, typing.Any] = None) -> None:
        thread = threading.Thread(target=target, args=args, kwargs=kwargs)
        thread.start()

        now = datetime.datetime.now()
        self._threads.append((thread, now,))

    @synchronized
    def sync(self) -> None:
        for thread, started_at in self._threads:
            thread.join()

        self._threads.clear()

    @synchronized
    def part_sync(self) -> None:
        now = datetime.datetime.now()

        while self._threads:
            thread, started_at = self._threads[0]

            if now - started_at > self._timedelta_for_part_sync:
                thread.join()
                self._threads.popleft()
            else:
                break


class TaskQueue:
    _tasks: typing.Deque[typing.Tuple[typing.Callable, tuple, typing.Dict[str, typing.Any]]]
    _lock: threading.Lock
    _thread: threading.Thread
    _on_close: typing.Optional[typing.Callable]
    _is_stopped: bool = False

    def __init__(self, *, on_close: typing.Optional[typing.Callable] = None) -> None:
        self._tasks = collections.deque()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._process_tasks)
        self._thread.start()
        self._on_close = on_close

    def __len__(self) -> int:
        return len(self._tasks)

    def push(self,
             target: typing.Callable,
             args: tuple = None,
             kwargs: typing.Dict[str, typing.Any] = None, *,
             is_high: bool = False) -> None:
        if self._is_stopped:
            return

        if args is None:
            args = tuple()

        if kwargs is None:
            kwargs = {}

        if is_high:
            self._tasks.appendleft((target, args, kwargs,))
        else:
            self._tasks.append((target, args, kwargs,))

    @synchronized
    def close(self) -> None:
        self._is_stopped = True
        self._thread.join()

    def _process_tasks(self) -> typing.NoReturn:
        while not self._is_stopped:
            try:
                task = self._tasks.popleft()
            except IndexError:
                task = None

            if task is None:
                sleep(1)
            else:
                try:
                    task[0](*task[1], **task[2])
                except Exception as e:
                    logging.exception(e)

        if self._on_close:
            self._on_close()
