import datetime
import logging
import queue
import threading
import typing
from time import sleep

from .constants import TaskPriorities
from .dto import RetryPolicy, Task, default_retry_policy
from .exceptions import RepeatTask
from ..common.utils import synchronized


__all__ = (
    'TaskQueue',
    'UniqueTaskQueue',
)


class TaskQueue:
    _tasks: queue.PriorityQueue
    _thread: threading.Thread
    _on_close: typing.Optional[typing.Callable]
    _is_stopped: threading.Event

    def __init__(self, *, on_close: typing.Optional[typing.Callable] = None) -> None:
        self._tasks = queue.PriorityQueue()
        self._on_close = on_close
        self._is_stopped = threading.Event()

        self._thread = threading.Thread(target=self._process_tasks)
        self._thread.start()

    def __len__(self) -> int:
        return self._tasks.qsize()

    def push(self,
             target: typing.Callable,
             args: typing.Optional[tuple] = None,
             kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None, *,
             priority: int = TaskPriorities.MEDIUM,
             retry_policy: RetryPolicy = default_retry_policy) -> typing.Optional[Task]:
        if self._is_stopped.is_set():
            return None

        task = Task.create(
            priority=priority,
            target=target,
            args=args,
            kwargs=kwargs,
            retry_policy=retry_policy,
        )

        self.push_task(task)

        return task

    def push_task(self, task: Task) -> None:
        self._tasks.put(task)

    def close(self) -> None:
        self._is_stopped.set()
        self._thread.join()

    def _process_tasks(self) -> typing.NoReturn:
        while not self._is_stopped.is_set():
            try:
                task: typing.Optional[Task] = self._tasks.get(block=False)
            except queue.Empty:
                task = None

            if task is None:
                sleep(1)
                continue

            if task.run_after > datetime.datetime.now():
                sleep(1)
                self.push_task(task)
                continue

            try:
                task.run()
            except RepeatTask:
                self.push_task(task)

        if len(self):
            logging.warning(f'TaskQueue is stopping, but there are {len(self)} tasks in queue.')

        if self._on_close:
            self._on_close()


class UniqueTaskQueue:
    _lock: threading.Lock
    _tasks_map: typing.Dict[typing.Callable, threading.Event]
    _task_queue: TaskQueue

    def __init__(self, *, task_queue: TaskQueue) -> None:
        self._task_queue = task_queue
        self._tasks_map = {}
        self._lock = threading.Lock()

    def push(self,
             target: typing.Callable, *,
             priority: int = TaskPriorities.MEDIUM) -> typing.Optional[Task]:
        if not self._task_is_finished(target):
            return None

        task = self._task_queue.push(target, priority=priority)

        if task is not None:
            self._track(task)

        return task

    @synchronized
    def _track(self, task: Task) -> None:
        self._tasks_map[task.target] = task.is_finished

    @synchronized
    def _task_is_finished(self, target: typing.Callable) -> bool:
        if target not in self._tasks_map:
            return True

        if self._tasks_map[target].is_set():
            del self._tasks_map[target]
            return True

        return False
