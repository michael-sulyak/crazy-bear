import logging
import queue
import threading
import typing
from functools import partial
from time import sleep

from .. import constants
from ..base import BaseTaskQueue, BaseWorker, TaskPriorityQueue
from ..dto import Task
from ..middlewares import BaseMiddleware


__all__ = (
    'MemTaskQueue',
    'ThreadWorker',
)


class MemTaskQueue(BaseTaskQueue):
    _tasks: TaskPriorityQueue

    def __init__(self) -> None:
        self._tasks = TaskPriorityQueue()

    def __len__(self) -> int:
        return self._tasks.qsize()

    def put_task(self, task: Task) -> None:
        task.status = constants.TaskStatuses.PENDING
        logging.debug('Put %s to MemTaskQueue', task)
        self._tasks.put(task)

    def get(self) -> typing.Optional[Task]:
        try:
            return self._tasks.get(block=False)
        except queue.Empty:
            return None


class ThreadWorker(BaseWorker):
    task_queue: BaseTaskQueue
    middlewares: typing.Tuple[BaseMiddleware, ...]
    _middleware_chain: typing.Callable
    _is_run: threading.Event
    _thread: threading.Thread
    _on_close: typing.Optional[typing.Callable]
    _getting_delay: float = 0.1

    def __init__(self, *,
                 task_queue: BaseTaskQueue,
                 on_close: typing.Optional[typing.Callable] = None,
                 middlewares: typing.Tuple[BaseMiddleware, ...]) -> None:
        self.task_queue = task_queue
        self.middlewares = middlewares
        self._on_close = on_close
        self._is_run = threading.Event()
        self._thread = threading.Thread(target=self._process_tasks)

        self._middleware_chain = self._run_task

        for middleware in reversed(self.middlewares):
            self._middleware_chain = partial(
                middleware.process,
                handler=self._middleware_chain,
                task_queue=self.task_queue,
            )

    @property
    def is_run(self) -> bool:
        return self._is_run.is_set()

    def run(self) -> None:
        if self.is_run:
            return

        logging.info(f'Run {self.__class__.__name__}...')
        self._is_run.set()
        self._thread.start()
        logging.info(f'{self.__class__.__name__} is ready.')

    def stop(self) -> None:
        if not self.is_run:
            return

        self._is_run.clear()

        if len(self.task_queue):
            logging.warning(f'TaskQueue is stopped, but there are {len(self.task_queue)} tasks in queue.')

        self._thread.join()

    def _process_tasks(self) -> typing.NoReturn:
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
