import abc
import bisect
import datetime
import typing
from heapq import heappop, heappush
from queue import Empty, Queue

from .constants import TaskPriorities
from .dto import Task


__all__ = (
    'BaseTaskQueue',
    'BaseWorker',
    'TaskPriorityQueue',
)


class TaskPriorityQueue(Queue):
    queue_map: typing.Dict[int, typing.List[tuple[typing.Any, Task]]]
    priorities: typing.List[int]

    def _init(self, maxsize) -> None:
        self.queue_map = {}
        self.priorities = []

    def _qsize(self) -> int:
        return sum(len(x) for x in self.queue_map.values())

    def _put(self, task: Task) -> None:
        if task.priority not in self.queue_map:
            self.queue_map[task.priority] = []
            bisect.insort(self.priorities, task.priority)

        heappush(self.queue_map[task.priority], (task.run_after, task,))

    def _get(self) -> typing.Optional[Task]:
        now = datetime.datetime.now()

        for priority in self.priorities:
            queue = self.queue_map[priority]

            if not queue:
                continue

            if queue[0][1].run_after <= now:
                return heappop(queue)[1]

        raise Empty


class BaseTaskQueue(abc.ABC):
    @abc.abstractmethod
    def __len__(self) -> int:
        pass

    def put(self,
            target: typing.Callable,
            args: typing.Optional[tuple] = None,
            kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None, *,
            priority: int = TaskPriorities.MEDIUM,
            run_after: typing.Optional[datetime.datetime] = None) -> typing.Optional[Task]:
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
    def get(self) -> typing.Optional[Task]:
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
