import datetime
import logging
import threading
import typing
from dataclasses import dataclass, field

from .constants import TaskPriorities
from .exceptions import BaseTaskQueueException, RepeatTask


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
    received_at: datetime.datetime = field(
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
    retry_policy: RetryPolicy = field(
        compare=False,
        default=default_retry_policy,
    )
    _lock: threading.Lock = field(
        compare=False,
        default_factory=threading.Lock,
    )
    _retries: int = field(
        compare=False,
        default=0,
    )

    def __call__(self, *args, **kwargs) -> typing.Any:
        return self.target(*self.args, **self.kwargs)

    @classmethod
    def create(cls,
               target: typing.Callable,
               args: typing.Optional[tuple] = None,
               kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None, *,
               priority: int = TaskPriorities.MEDIUM,
               retry_policy: RetryPolicy = default_retry_policy) -> 'Task':
        if args is None:
            args = tuple()

        if kwargs is None:
            kwargs = {}

        task = cls(target=target, args=args, kwargs=kwargs, priority=priority, retry_policy=retry_policy)
        task.is_pending.set()
        return task

    def run(self) -> None:
        self.is_processing.set()
        self.is_pending.clear()

        try:
            with self.retry_policy:
                self.result = self()
        except RepeatTask as e:
            self._retries += 1

            with self._lock:
                if e.after:
                    self.run_after = datetime.datetime.now() + e.after
                    self.priority = TaskPriorities.LOW

                if self.retry_policy.max_retries <= self._retries:
                    logging.info(f'Retry policy for {self}')
                    raise
        except BaseTaskQueueException:
            raise
        except Exception as e:
            self.error = e
            logging.exception(e)
        finally:
            self.is_finished.set()
            self.is_processing.clear()
