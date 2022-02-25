import abc
import datetime
import logging
import threading
import typing
from dataclasses import dataclass, field

from crontab import CronTab

from . import constants
from .exceptions import BaseTaskQueueException, RepeatTask
from ..common.utils import log_func_performance, synchronized_method


__all__ = (
    'Task',
    'IntervalTask',
    'RepeatableTask',
    'DelayedTask',
    'ScheduledTask',
    'RetryPolicy',
    'RetryPolicyForConnectionError',
    'default_retry_policy',
    'retry_policy_for_connection_error',
)


@dataclass
class RetryPolicy:
    max_retries: float = 3
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


@dataclass(eq=False)
class Task:
    priority: int
    target: typing.Callable
    args: tuple = field(
        default_factory=tuple,
    )
    kwargs: typing.Dict[str, typing.Any] = field(
        default_factory=dict,
    )
    run_after: datetime.datetime = field(
        default_factory=datetime.datetime.now,
    )
    result: typing.Any = field(
        default=None,
    )
    error: typing.Optional[Exception] = field(
        default=None,
    )
    retry_policy: RetryPolicy = field(
        default=default_retry_policy,
    )
    _status: str = field(
        default=constants.TaskStatus.CREATED,
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
    )
    _retries: int = field(
        default=0,
    )

    def __post_init__(self) -> None:
        self.target = log_func_performance(self.__class__.__name__.lower())(self.target)

    @property
    @synchronized_method
    def status(self) -> str:
        return self._status

    @status.setter
    @synchronized_method
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
        with self._lock:
            if self._status == constants.TaskStatus.CANCELED:
                return

            self._status = constants.TaskStatus.STARTED
            self.result = None
            self.error = None

        try:
            with self.retry_policy:
                self.result = self.call()
        except RepeatTask as e:
            logging.debug(e)

            self._retries += 1

            with self._lock:
                if e.after:
                    self.run_after = datetime.datetime.now() + e.after
                    self.priority = constants.TaskPriorities.LOW

                if self._retries <= self.retry_policy.max_retries:
                    logging.info(f'Retry policy for {self}')
                    raise

            with self._lock:
                self.error = e.source
                self._status = constants.TaskStatus.FAILED

            logging.warning(e.source, exc_info=True)
        except Exception as e:
            with self._lock:
                self.error = e
                self._status = constants.TaskStatus.FAILED

            logging.exception(e)
        else:
            self.status = constants.TaskStatus.FINISHED

    def call(self) -> typing.Any:
        return self.target(*self.args, **self.kwargs)

    @synchronized_method
    def cancel(self) -> bool:
        is_success = self._status in (constants.TaskStatus.CREATED, constants.TaskStatus.PENDING,)
        self._status = constants.TaskStatus.CANCELED
        return is_success


class RepeatableTask(Task):
    pass


@dataclass(eq=False)
class IntervalTask(RepeatableTask):
    interval: datetime.timedelta = field(
        default=None,
    )
    run_immediately: bool = field(
        default=True,
    )

    def __post_init__(self) -> None:
        super().__post_init__()

        if not self.run_immediately:
            self.run_after = datetime.datetime.now() + self.interval

    def run(self) -> None:
        logging.debug('Run interval %s', self)
        super().run()

        with self._lock:
            if self._status != constants.TaskStatus.CANCELED:
                self._retries = 0
                self.run_after = datetime.datetime.now() + self.interval
                logging.debug('Repeat %s after %s', self, self.run_after)
                raise RepeatTask(source=None)


@dataclass(eq=False)
class DelayedTask(RepeatableTask):
    delay: datetime.timedelta = field(
        default=None,
    )

    def __post_init__(self) -> None:
        super().__post_init__()

        self.run_after = self.run_after + self.delay


@dataclass(eq=False)
class ScheduledTask(RepeatableTask):
    crontab: CronTab = field(
        default=None,
    )

    def __post_init__(self) -> None:
        super().__post_init__()

        self.run_after = self.crontab.next(self.run_after, default_utc=False, return_datetime=True)

    def run(self) -> None:
        logging.debug('Run scheduled %s', self)
        super().run()

        with self._lock:
            if self._status != constants.TaskStatus.CANCELED:
                self._retries = 0
                self.run_after = self.crontab.next(default_utc=False, return_datetime=True)
                logging.debug('Repeat %s after %s', self, self.run_after)
                raise RepeatTask(source=None)
