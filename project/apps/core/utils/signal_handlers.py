import abc
import dataclasses
import datetime
import io
import typing

from .. import constants, events
from ...common.events import Receiver
from ...common.utils import get_cpu_temp, current_time, get_weather, get_ram_usage, get_free_disk_space, create_plot
from ...messengers.base import BaseMessenger
from ...signals.models import Signal
from ...task_queue import IntervalTask, Task, TaskPriorities
from ....config.utils import NOTHING


@dataclasses.dataclass
class NotificationParams:
    condition: typing.Callable
    message: str
    delay: datetime.timedelta


class BaseSignalHandler(abc.ABC):
    task_interval: datetime.timedelta
    _messenger: BaseMessenger

    def __init__(self, *, messenger: BaseMessenger) -> None:
        self._messenger = messenger

    def get_tasks(self) -> tuple[Task, ...]:
        return (
            IntervalTask(
                target=self.process,
                priority=TaskPriorities.LOW,
                interval=self.task_interval,
                run_after=datetime.datetime.now() + datetime.timedelta(seconds=10),
            ),
        )

    def get_signals(self) -> tuple[Receiver, ...]:
        return (
            events.request_for_statistics.connect(self.create_plot),
        )

    @abc.abstractmethod
    def process(self) -> None:
        pass

    @abc.abstractmethod
    def compress(self) -> None:
        pass

    def create_plot(self, *,
                    date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                    components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
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

        now = current_time()

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


class CpuTempHandler(BaseAdvancedSignalHandler):
    signal_type = constants.CPU_TEMPERATURE
    task_interval = datetime.timedelta(seconds=10)
    compress_by_time = True
    list_of_notification_params = (
        NotificationParams(
            condition=lambda x: x > 90,
            message='CPU temperature is high!',
            delay=datetime.timedelta(minutes=10),
        ),
        NotificationParams(
            condition=lambda x: x > 65,
            message='CPU temperature is very high!',
            delay=datetime.timedelta(hours=1),
        ),
    )

    def get_value(self) -> typing.Any:
        try:
            return get_cpu_temp()
        except RuntimeError:
            return NOTHING

    def create_plot(self, *,
                    date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                    components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        cpu_temp_stats = Signal.get_aggregated(
            signal_type=constants.CPU_TEMPERATURE,
            datetime_range=date_range,
        )

        if not cpu_temp_stats:
            return None

        return create_plot(
            title='CPU temperature',
            x_attr='aggregated_time',
            y_attr='value',
            stats=cpu_temp_stats,
        )


class WeatherHandler(BaseSignalHandler):
    task_interval = datetime.timedelta(minutes=5)

    def process(self) -> None:
        weather = get_weather()
        now = current_time()

        Signal.bulk_add((
            Signal(type=constants.WEATHER_TEMPERATURE, value=weather['main']['temp'], received_at=now),
            Signal(type=constants.WEATHER_HUMIDITY, value=weather['main']['humidity'], received_at=now),
        ))

    def compress(self) -> None:
        signal_types = (
            constants.WEATHER_TEMPERATURE,
            constants.WEATHER_HUMIDITY,
        )
        Signal.clear(signal_types)

        now = current_time()

        datetime_range = (
            now - datetime.timedelta(hours=3),
            now - datetime.timedelta(minutes=5),
        )

        for signal_type in signal_types:
            Signal.compress_by_time(
                signal_type,
                datetime_range=datetime_range,
            )

            Signal.compress(
                signal_type,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )


class RamUsageHandler(BaseAdvancedSignalHandler):
    signal_type = constants.RAM_USAGE
    task_interval = datetime.timedelta(seconds=10)
    compress_by_time = True
    list_of_notification_params = (
        NotificationParams(
            condition=lambda x: x > 90,
            message='Running out of RAM!!!',
            delay=datetime.timedelta(hours=1),
        ),
        NotificationParams(
            condition=lambda x: x > 60,
            message='Running out of RAM!',
            delay=datetime.timedelta(hours=3),
        ),
    )

    def get_value(self) -> typing.Any:
        return round(get_ram_usage() * 100, 2)

    def create_plot(self, *,
                    date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                    components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        ram_stats = Signal.get_aggregated(
            signal_type=constants.RAM_USAGE,
            datetime_range=date_range,
        )

        if not ram_stats:
            return None

        return create_plot(
            title='RAM usage (%)',
            x_attr='aggregated_time',
            y_attr='value',
            stats=ram_stats,
        )


class FreeDiskSpaceHandler(BaseAdvancedSignalHandler):
    signal_type = constants.FREE_DISK_SPACE
    task_interval = datetime.timedelta(minutes=1)
    compress_by_time = True
    list_of_notification_params = (
        NotificationParams(
            condition=lambda x: x < 1024,
            message='There is very little disk space left!',
            delay=datetime.timedelta(hours=1),
        ),
        NotificationParams(
            condition=lambda x: x < 500,
            message='There is little disk space left!',
            delay=datetime.timedelta(hours=6),
        ),
    )

    def get_value(self) -> typing.Any:
        return get_free_disk_space()

    def create_plot(self, *,
                    date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                    components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
        if 'inner_stats' not in components:
            return None

        free_disk_space_stats = Signal.get_aggregated(
            signal_type=constants.FREE_DISK_SPACE,
            datetime_range=date_range,
        )

        if not free_disk_space_stats:
            return None

        return create_plot(
            title='Free disk space (MB)',
            x_attr='aggregated_time',
            y_attr='value',
            stats=free_disk_space_stats,
        )


class SupremeSignalHandler:
    handlers: tuple[typing.Type[BaseAdvancedSignalHandler], ...] = (
        CpuTempHandler,
        WeatherHandler,
        RamUsageHandler,
        FreeDiskSpaceHandler,
    )
    _inited_handlers: tuple[BaseAdvancedSignalHandler, ...]

    def __init__(self, *, messenger: BaseMessenger) -> None:
        self._inited_handlers = tuple(
            handler(messenger=messenger)
            for handler in self.handlers
        )

    def get_tasks(self) -> tuple[Task, ...]:
        tasks = []

        for handler in self._inited_handlers:
            tasks.extend(handler.get_tasks())

        return tuple(tasks)

    def get_signals(self) -> tuple[Receiver, ...]:
        signals = []

        for handler in self._inited_handlers:
            signals.extend(handler.get_signals())

        return tuple(signals)

    def compress(self) -> None:
        for handler in self._inited_handlers:
            handler.compress()
