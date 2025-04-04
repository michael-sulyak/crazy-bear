import abc
import dataclasses
import datetime
import io
import typing

from libs import task_queue
from libs.messengers.base import BaseMessenger
from libs.task_queue import BaseTaskQueue

from ...common.constants import NOTHING
from ...common.events import Receiver
from ...common.state import State
from ...signals.models import Signal
from .. import events
from ..base import ModuleContext
from .utils import get_default_signal_compress_datetime_range


@dataclasses.dataclass
class NotificationParams:
    condition: typing.Callable
    message: str
    delay: datetime.timedelta


class BaseSignalHandler(abc.ABC):
    _messenger: BaseMessenger
    _state: State
    _task_queue: BaseTaskQueue

    def __init__(self, *, context: ModuleContext) -> None:
        self._context = context
        self._messenger = context.messenger
        self._state = context.state
        self._task_queue = context.task_queue

    def get_tasks(self) -> tuple[task_queue.Task, ...]:
        return ()

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {}

    def subscribe_to_events(self) -> tuple[Receiver, ...]:
        return (events.request_for_statistics.connect(self.generate_plots),)

    def compress(self) -> None:
        pass

    def generate_plots(
        self,
        *,
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> typing.Sequence[io.BytesIO] | None:
        return None

    def disable(self) -> None:
        pass


class IntervalNotificationCheckMixin(abc.ABC):
    task_interval: datetime.timedelta
    priority = task_queue.TaskPriorities.LOW

    def get_tasks(self) -> tuple[task_queue.Task, ...]:
        return (
            task_queue.IntervalTask(
                target=self.process,
                priority=self.priority,
                interval=self.task_interval,
                run_after=datetime.datetime.now() + datetime.timedelta(seconds=10),
            ),
        )

    @abc.abstractmethod
    def process(self) -> None:
        pass


class SignalNotificationMixin(abc.ABC):
    list_of_notification_params: tuple[NotificationParams, ...] = ()
    _last_notified_at: datetime.datetime = datetime.datetime.min

    def _check_notifications(self, value: typing.Any) -> None:
        for notification_params in self.list_of_notification_params:
            if not notification_params.condition(value):
                continue

            now = datetime.datetime.now()

            if now - self._last_notified_at > notification_params.delay:
                self._messenger.send_message(notification_params.message)
                self._last_notified_at = now

            break


class BaseSimpleSignalHandler(SignalNotificationMixin, IntervalNotificationCheckMixin, BaseSignalHandler, abc.ABC):
    signal_type: str
    compress_by_time: bool
    approximation_value: float = 0

    def process(self) -> None:
        value = self.get_value()

        if value is NOTHING:
            return

        Signal.add(signal_type=self.signal_type, value=value)
        self._check_notifications(value)

    @abc.abstractmethod
    def get_value(self) -> typing.Any:
        pass

    def compress(self) -> None:
        datetime_range = get_default_signal_compress_datetime_range()

        if self.compress_by_time:
            Signal.compress_by_time(
                self.signal_type,
                datetime_range=datetime_range,
            )

        Signal.compress(
            self.signal_type,
            datetime_range=datetime_range,
            approximation_value=self.approximation_value,
            approximation_time=datetime.timedelta(hours=1),
        )
