import logging
import queue
import threading
import typing
from dataclasses import dataclass, field
from time import sleep

from .utils import synchronized


__all__ = (
    'Task',
    'TaskQueue',
    'TaskPriorities',
    'UniqueTaskQueue',
)


class TaskPriorities:
    LOW = 3
    MEDIUM = 2
    HIGH = 1


@dataclass(order=True)
class Task:
    priority: int
    target: typing.Callable = field(
        compare=False,
    )
    args: tuple = field(
        compare=False,
    )
    kwargs: typing.Dict[str, typing.Any] = field(
        compare=False,
    )
    result: typing.Any = field(
        compare=False,
        default=None,
    )
    error: typing.Optional[Exception] = field(
        compare=False,
        default=None,
    )
    is_pending: threading.Event = field(
        compare=False,
        default_factory=threading.Event,
    )
    is_processing: threading.Event = field(
        compare=False,
        default_factory=threading.Event,
    )
    is_finished: threading.Event = field(
        compare=False,
        default_factory=threading.Event,
    )

    def __call__(self, *args, **kwargs) -> typing.Any:
        return self.target(*self.args, **self.kwargs)

    @classmethod
    def create(cls,
               target: typing.Callable,
               args: tuple = None,
               kwargs: typing.Dict[str, typing.Any] = None, *,
               priority: int = TaskPriorities.MEDIUM) -> 'Task':
        task = cls(target=target, args=args, kwargs=kwargs, priority=priority)
        task.is_pending.set()
        return task

    def run(self) -> None:
        self.is_processing.set()
        self.is_pending.clear()

        try:
            self.result = self()
        except Exception as e:
            self.error = e
            logging.exception(e)
        finally:
            self.is_finished.set()
            self.is_processing.clear()


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
             args: tuple = None,
             kwargs: typing.Dict[str, typing.Any] = None, *,
             priority: int = TaskPriorities.MEDIUM) -> typing.Optional[Task]:
        if self._is_stopped.is_set():
            return None

        if args is None:
            args = tuple()

        if kwargs is None:
            kwargs = {}

        task = Task.create(
            priority=priority,
            target=target,
            args=args,
            kwargs=kwargs,
        )

        self._tasks.put(task)

        return task

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
            else:
                task.run()

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
