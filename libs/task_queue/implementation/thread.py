import bisect
import datetime
import logging
import threading
import typing
from functools import partial
from heapq import heappop, heappush
from time import sleep

from ...casual_utils.parallel_computing import synchronized_method
from .. import constants
from ..base import BaseTaskQueue, BaseWorker
from ..dto import Task
from ..middlewares import BaseMiddleware


__all__ = (
    'MemTaskQueue',
    'ThreadWorker',
)


class MemTaskQueue(BaseTaskQueue):
    _queue_map: dict[int, list[tuple[typing.Any, Task]]]
    _priorities: list[int]
    _lock: threading.Lock

    def __init__(self) -> None:
        self._queue_map = {}
        self._priorities = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return sum(len(x) for x in self._queue_map.values())

    @synchronized_method
    def put_task(self, task: Task) -> None:
        task.status = constants.TaskStatuses.PENDING
        logging.debug('Put %s to MemTaskQueue', task)

        if task.priority not in self._queue_map:
            self._queue_map[task.priority] = []
            bisect.insort(self._priorities, task.priority)

        heappush(
            self._queue_map[task.priority],
            (
                task.run_after,
                task,
            ),
        )

    @synchronized_method
    def get(self) -> Task | None:
        now = datetime.datetime.now()

        for priority in self._priorities:
            queue = self._queue_map[priority]

            if not queue:
                continue

            if queue[0][1].run_after <= now:
                return heappop(queue)[1]

        return None


class ThreadWorker(BaseWorker):
    task_queue: BaseTaskQueue
    middlewares: tuple[BaseMiddleware, ...]
    _middleware_chain: typing.Callable
    _is_run: threading.Event
    _threads: tuple[threading.Thread, ...]
    _on_close: typing.Callable | None
    _getting_delay: float = 0.1

    def __init__(
        self,
        *,
        task_queue: BaseTaskQueue,
        on_close: typing.Callable | None = None,
        middlewares: tuple[BaseMiddleware, ...],
        count: int = 1,
    ) -> None:
        self.task_queue = task_queue
        self.middlewares = middlewares
        self._on_close = on_close
        self._is_run = threading.Event()

        self._middleware_chain = self._run_task

        for middleware in reversed(self.middlewares):
            self._middleware_chain = partial(
                middleware.process,
                handler=self._middleware_chain,
                task_queue=self.task_queue,
            )

        self._threads = tuple(threading.Thread(target=self._process_tasks) for _ in range(count))

    @property
    def is_run(self) -> bool:
        return self._is_run.is_set()

    def run(self) -> None:
        if self.is_run:
            return

        logging.debug(f'Run {self.__class__.__name__}...')
        self._is_run.set()

        for thread in self._threads:
            thread.start()

        logging.debug(f'{self.__class__.__name__} is ready.')

    def stop(self) -> None:
        if not self.is_run:
            return

        self._is_run.clear()

        if len(self.task_queue):
            logging.warning(f'TaskQueue is stopped, but there are {len(self.task_queue)} tasks in queue.')

        for thread in self._threads:
            thread.join()

    def _process_tasks(self) -> None:
        logging.debug('Running worker #%s...', threading.get_native_id())

        while self.is_run:
            task = self.task_queue.get()

            if task is None:
                logging.debug('Wait tasks')
                sleep(self._getting_delay)
                continue

            logging.debug('Get %s from MemTaskQueue', task)

            try:
                self._middleware_chain(task=task)
            except Exception as e:
                logging.exception(e)

        if self._on_close is not None:
            self._on_close()

    @staticmethod
    def _run_task(*, task: Task) -> typing.Any:
        return task.run()
