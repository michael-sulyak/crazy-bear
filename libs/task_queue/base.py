import abc
import datetime
import typing

from .constants import TaskPriorities
from .dto import Task


__all__ = (
    'BaseTaskQueue',
    'BaseWorker',
)


class BaseTaskQueue(abc.ABC):
    @abc.abstractmethod
    def __len__(self) -> int:
        pass

    def put(
        self,
        target: typing.Callable,
        args: tuple | None = None,
        kwargs: dict[str, typing.Any] | None = None,
        *,
        priority: int = TaskPriorities.MEDIUM,
        run_after: datetime.datetime | None = None,
    ) -> Task | None:
        if run_after is None:
            run_after = datetime.datetime.now()

        task = Task.create(
            priority=priority,
            target=target,
            args=args,
            kwargs=kwargs,
            run_after=run_after,
        )

        self.put_task(task)

        return task

    @abc.abstractmethod
    def put_task(self, task: Task) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> Task | None:
        pass


class BaseWorker(abc.ABC):
    @property
    @abc.abstractmethod
    def is_run(self) -> bool:
        pass

    @abc.abstractmethod
    def run(self) -> None:
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        pass
