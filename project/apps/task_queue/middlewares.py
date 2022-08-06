import abc
import datetime
import logging
import typing

from . import BaseTaskQueue, Task, constants, exceptions as task_exceptions
from ..common.utils import log_performance


class BaseMiddleware(abc.ABC):
    def __init__(self, *args, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def process(self, *, task: Task, task_queue: BaseTaskQueue, handler: typing.Callable) -> typing.Any:
        pass


class SupportOfRetries(BaseMiddleware):
    def process(self, *, task: Task, task_queue: BaseTaskQueue, handler: typing.Callable) -> typing.Any:
        try:
            return handler(task=task)
        except task_exceptions.RepeatTask as e:
            task.run_after = e.after
            logging.info('Retrying %s', task)
            task_queue.put_task(task)


class ConcreteRetries(BaseMiddleware):
    """
    Need to be before `SupportOfRetries`.
    """

    max_retries: float
    exceptions: typing.Tuple[typing.Type[Exception], ...]

    def __init__(self, *,
                 max_retries: float = 3,
                 exceptions: typing.Tuple[typing.Type[Exception], ...] = (Exception,)) -> None:
        super().__init__()

        self.max_retries = max_retries
        self.exceptions = exceptions

    def process(self, *, task: Task, task_queue: BaseTaskQueue, handler: typing.Callable) -> typing.Any:
        result = None

        try:
            result = handler(task=task)
        except self.exceptions as e:
            with task._lock:
                retries = task.options.setdefault('retries', 0)
                retries += 1

                task.options['retries'] = retries
                task.options['exception'] = e

                if retries <= self.max_retries:
                    logging.info('Retry policy for %s', task)
                    raise task_exceptions.RepeatTask(delay=self._get_retry_delay(retries))

                task.error = e.source
                task.status = constants.TaskStatuses.FAILED
        else:
            with task._lock:
                task.options['retries'] = 0

        return result

    @staticmethod
    def _get_retry_delay(retries: int) -> datetime.timedelta:
        delay = datetime.timedelta(seconds=retries ** 4 + 10)

        if delay > datetime.timedelta(minutes=30):
            delay = datetime.timedelta(minutes=30)

        return delay


class PerformanceLogging(BaseMiddleware):
    def process(self, *, task: Task, task_queue: BaseTaskQueue, handler: typing.Callable) -> typing.Any:
        func_name = f'{task.target.__module__}.{task.target.__qualname__}'

        with log_performance(task.__class__.__name__.lower(), func_name):
            return handler(task=task)


class ExceptionLogging(BaseMiddleware):
    def process(self, *, task: Task, task_queue: BaseTaskQueue, handler: typing.Callable) -> typing.Any:
        try:
            return handler(task=task)
        except Exception as e:
            logging.exception(e)
            task.error = e
            task.status = constants.TaskStatuses.FAILED
            return None
