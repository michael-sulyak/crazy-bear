import collections
import datetime
import logging
import queue
import threading
import typing
from dataclasses import dataclass, field
from time import sleep

from .models import Signal
from .utils import synchronized
from ..core.constants import TASK_QUEUE_PUSH


__all__ = (
    'TaskQueue',
    'TaskQueueWithStats',
)


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


@dataclass(order=True)
class _Task:
    priority: int

    target: typing.Callable = field(compare=False)
    args: tuple = field(compare=False)
    kwargs: typing.Dict[str, typing.Any] = field(compare=False)

    def __call__(self, *args, **kwargs) -> typing.Any:
        return self.target(*self.args, **self.kwargs)


class TaskQueue:
    _tasks: queue.PriorityQueue
    _lock: threading.Lock
    _thread: threading.Thread
    _on_close: typing.Optional[typing.Callable]
    _is_stopped: bool = False

    def __init__(self, *, on_close: typing.Optional[typing.Callable] = None) -> None:
        self._tasks = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._process_tasks)
        self._thread.start()
        self._on_close = on_close

    @property
    def approximate_size(self) -> int:
        return self._tasks.qsize()

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

        task = _Task(
            priority=1 if is_high else 2,
            target=target,
            args=args,
            kwargs=kwargs,
        )

        self._tasks.put(task)

    @synchronized
    def close(self) -> None:
        self._is_stopped = True
        self._thread.join()

    def _process_tasks(self) -> typing.NoReturn:
        while not self._is_stopped:
            try:
                _, task = self._tasks.get()
            except IndexError:
                task = None

            if task is None:
                sleep(1)
            else:
                try:
                    task()
                except Exception as e:
                    logging.exception(e)

        if self._on_close:
            self._on_close()


class TaskQueueWithStats(TaskQueue):
    _history: typing.Deque[Signal]
    _max_history = 100

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._history = collections.deque()

    def push(self, *args, **kwargs) -> None:
        if self._is_stopped:
            return

        super().push(*args, **kwargs)

        self._history.append(Signal(
            type=TASK_QUEUE_PUSH,
            value=1,
            received_at=datetime.datetime.now(),
        ))

        if len(self._history) > self._max_history:
            self.save_history()

    @synchronized
    def save_history(self) -> None:
        history = []

        for _ in range(self._max_history):
            try:
                history.append(self._history.popleft())
            except IndexError:
                break

        if history:
            Signal.bulk_add(history)
