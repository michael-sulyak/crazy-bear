import datetime
import logging
import threading
import typing
from dataclasses import dataclass, field

from . import constants
from .exceptions import BaseTaskQueueException, RepeatTask
from ..common.utils import synchronized


__all__ = (
    'Task',
    'RetryPolicy',
    'RetryPolicyForConnectionError',
    'default_retry_policy',
    'retry_policy_for_connection_error',
)


@dataclass
class RetryPolicy:
    max_retries: int = 3
    exceptions: typing.Tuple = (Exception,)
    retry_delay: typing.Optional[datetime.timedelta] = datetime.timedelta(seconds=30)

    def __enter__(self) -> 'RetryPolicy':
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> bool:
        if exc_type is None:
            return True

        if issubclass(exc_type, BaseTaskQueueException) or not issubclass(exc_type, self.exceptions):
            return False

        raise RepeatTask(source=exc_value)


class RetryPolicyForConnectionError(RetryPolicy):
    exceptions: typing.Tuple = (ConnectionError,)


default_retry_policy = RetryPolicy(max_retries=0)
retry_policy_for_connection_error = RetryPolicy(exceptions=(ConnectionError,))


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
    run_after: datetime.datetime = field(
        default_factory=datetime.datetime.now,
    )
    result: typing.Any = field(
        compare=False,
        default=None,
    )
    error: typing.Optional[Exception] = field(
        compare=False,
        default=None,
    )
    retry_policy: RetryPolicy = field(
        compare=False,
        default=default_retry_policy,
    )
    _status: str = field(
        compare=False,
        default=constants.TaskStatus.CREATED,
    )
    _lock: threading.Lock = field(
        compare=False,
        default_factory=threading.Lock,
    )
    _retries: int = field(
        compare=False,
        default=0,
    )

    @property
    @synchronized
    def status(self) -> str:
        return self._status

    @status.setter
    @synchronized
    def status(self, value: str) -> None:
        self._status = value

    @classmethod
    def create(cls,
               target: typing.Callable,
               args: typing.Optional[tuple] = None,
               kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
               **params) -> 'Task':
        if args is None:
            args = tuple()

        if kwargs is None:
            kwargs = {}

        task = cls(target=target, args=args, kwargs=kwargs, **params)

        return task

    def run(self) -> None:
        self.status = constants.TaskStatus.STARTED

        try:
            with self.retry_policy:
                self.result = self.call()
        except RepeatTask as e:
            self._retries += 1

            with self._lock:
                if e.after:
                    self.run_after = datetime.datetime.now() + e.after
                    self.priority = constants.TaskPriorities.LOW

                if self.retry_policy.max_retries <= self._retries:
                    logging.info(f'Retry policy for {self}')
                    raise

            self.error = e.source
            self.status = constants.TaskStatus.FAILED
        except Exception as e:
            self.error = e
            self.status = constants.TaskStatus.FAILED
            logging.exception(e)
        else:
            self.status = constants.TaskStatus.FINISHED

    def call(self) -> typing.Any:
        return self.target(*self.args, **self.kwargs)
