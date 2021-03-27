import abc
import datetime
import typing

from .constants import TaskPriorities
from .dto import RetryPolicy, Task, default_retry_policy


__all__ = (
    'BaseTaskQueue',
    'BaseWorker',
)


class BaseTaskQueue(abc.ABC):
    @abc.abstractmethod
    def __len__(self) -> int:
        pass

    def put(self,
            target: typing.Callable,
            args: typing.Optional[tuple] = None,
            kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None, *,
            priority: int = TaskPriorities.MEDIUM,
            retry_policy: RetryPolicy = default_retry_policy,
            run_after: typing.Optional[datetime.datetime] = None) -> typing.Optional[Task]:
        if run_after is None:
            run_after = datetime.datetime.now()

        task = Task.create(
            priority=priority,
            target=target,
            args=args,
            kwargs=kwargs,
            retry_policy=retry_policy,
            run_after=run_after,
        )

        self.put_task(task)

        return task

    @abc.abstractmethod
    def put_task(self, task: Task) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> typing.Optional[Task]:
        pass


class BaseWorker(abc.ABC):
    is_run: bool

    @abc.abstractmethod
    def run(self) -> None:
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        pass
