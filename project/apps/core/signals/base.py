import abc
import dataclasses
import datetime
import io
import typing

from libs import task_queue
from libs.casual_utils.time import get_current_time
from libs.messengers.base import BaseMessenger
from .. import events
from ...common.events import Receiver
from ...common.state import State
from ...signals.models import Signal
from ....config.utils import NOTHING


@dataclasses.dataclass
class NotificationParams:
    condition: typing.Callable
    message: str
    delay: datetime.timedelta


class BaseSignalHandler(abc.ABC):
    task_interval: datetime.timedelta
    priority = task_queue.TaskPriorities.LOW
    _messenger: BaseMessenger
    _state: State

    def __init__(self, *, messenger: BaseMessenger, state: State) -> None:
        self._messenger = messenger
        self._state = state

    def get_tasks(self) -> tuple[task_queue.Task, ...]:
        return (
            task_queue.IntervalTask(
                target=self.process,
                priority=self.priority,
                interval=self.task_interval,
                run_after=datetime.datetime.now() + datetime.timedelta(seconds=10),
            ),
        )

    def get_signals(self) -> tuple[Receiver, ...]:
        return (
            events.request_for_statistics.connect(self.generate_plots),
        )

    @abc.abstractmethod
    def process(self) -> None:
        pass

    @abc.abstractmethod
    def compress(self) -> None:
        pass

    def generate_plots(self, *,
                       date_range: tuple[datetime.datetime, datetime.datetime],
                       components: typing.Set[str]) -> typing.Optional[typing.Sequence[io.BytesIO]]:
        return None


class BaseAdvancedSignalHandler(BaseSignalHandler, abc.ABC):
    signal_type: str
    list_of_notification_params: tuple[NotificationParams, ...] = ()
    compress_by_time: bool
    approximation_value: float = 0
    _last_notified_at: datetime.datetime = datetime.datetime.min

    def process(self) -> None:
        value = self.get_value()

        if value is NOTHING:
            return

        Signal.add(signal_type=self.signal_type, value=value)
        self._validate_value(value)

    @abc.abstractmethod
    def get_value(self) -> typing.Any:
        pass

    def compress(self) -> None:
        Signal.clear((self.signal_type,))

        now = get_current_time()

        datetime_range = (
            now - datetime.timedelta(hours=3),
            now - datetime.timedelta(minutes=5),
        )

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

    def _validate_value(self, value: typing.Any) -> None:
        for notification_params in self.list_of_notification_params:
            if not notification_params.condition(value):
                continue

            now = datetime.datetime.now()

            if now - self._last_notified_at > notification_params.delay:
                self._messenger.send_message(notification_params.message)
                self._last_notified_at = now

            break
