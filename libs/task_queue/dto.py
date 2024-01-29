import abc
import datetime
import logging
import threading
import typing
from dataclasses import dataclass, field

from crontab import CronTab

from . import constants, exceptions
from ..casual_utils.parallel_computing import synchronized_method


__all__ = (
    'Task',
    'IntervalTask',
    'RepeatableTask',
    'DelayedTask',
    'ScheduledTask',
)


@dataclass(kw_only=True, eq=False)
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
    options: typing.Dict[str, typing.Any] = field(
        default_factory=dict,
    )
    _status: str = field(
        default=constants.TaskStatuses.CREATED,
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
    )

    @property
    @synchronized_method
    def status(self) -> str:
        return self._status

    @status.setter
    @synchronized_method
    def status(self, value: str) -> None:
        self._status = value

    @classmethod
    def create(
        cls,
        target: typing.Callable,
        args: typing.Optional[tuple] = None,
        kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
        **params,
    ) -> 'Task':
        if args is None:
            args = tuple()

        if kwargs is None:
            kwargs = {}

        task = cls(target=target, args=args, kwargs=kwargs, **params)

        return task

    def run(self) -> None:
        with self._lock:
            if self._status == constants.TaskStatuses.CANCELED:
                return

            self._status = constants.TaskStatuses.STARTED
            self.result = None
            self.error = None

        try:
            self.result = self.call()
        except exceptions.BaseTaskQueueException:
            self.status = constants.TaskStatuses.FINISHED
            raise
        except Exception as e:
            with self._lock:
                self.error = e
                self._status = constants.TaskStatuses.FAILED

            raise
        else:
            self.status = constants.TaskStatuses.FINISHED

    def call(self) -> typing.Any:
        return self.target(*self.args, **self.kwargs)

    @synchronized_method
    def cancel(self) -> bool:
        is_success = self._status in (
            constants.TaskStatuses.CREATED,
            constants.TaskStatuses.PENDING,
        )
        self._status = constants.TaskStatuses.CANCELED
        return is_success

    def __lt__(self, other: 'Task') -> bool:
        # For ordering.
        return self.run_after < other.run_after


class RepeatableTask(Task, abc.ABC):
    pass


@dataclass(kw_only=True, eq=False)
class IntervalTask(RepeatableTask):
    interval: datetime.timedelta
    run_immediately: bool = field(
        default=True,
    )

    def __post_init__(self) -> None:
        if not self.run_immediately:
            self.run_after = datetime.datetime.now() + self.interval

    def run(self) -> None:
        logging.debug('Run interval %s', self)

        try:
            super().run()
        except Exception as e:
            logging.exception(e)

        with self._lock:
            if self._status != constants.TaskStatuses.CANCELED:
                logging.debug('Repeat %s after %s', self, self.run_after)
                raise exceptions.RepeatTask(delay=self.interval)


@dataclass(kw_only=True, eq=False)
class DelayedTask(RepeatableTask):
    delay: datetime.timedelta

    def __post_init__(self) -> None:
        self.run_after = self.run_after + self.delay


@dataclass(kw_only=True, eq=False)
class ScheduledTask(RepeatableTask):
    crontab: CronTab

    def __post_init__(self) -> None:
        self.run_after = self.crontab.next(self.run_after, default_utc=False, return_datetime=True)

    def run(self) -> None:
        logging.debug('Run scheduled %s', self)

        try:
            super().run()
        except Exception as e:
            logging.exception(e)

        with self._lock:
            if self._status != constants.TaskStatuses.CANCELED:
                logging.debug('Repeat %s after %s', self, self.run_after)
                raise exceptions.RepeatTask(after=self.crontab.next(default_utc=False, return_datetime=True))
