import datetime
import io
import typing

from crontab import CronTab

from libs.casual_utils.time import get_current_time
from libs.messengers.utils import ProgressBar
from libs.task_queue import IntervalTask, ScheduledTask, TaskPriorities

from ... import db
from ...common import interface
from ...common.utils import create_plot
from ...signals.models import Signal
from .. import constants, events
from ..base import BaseModule
from ..signals.supreme_handler import SupremeSignalHandler


__all__ = ('Signals',)


@interface.module(
    title='Signals',
    description='The module processes input signals.',
)
class Signals(BaseModule):
    _timedelta_for_ping: datetime.timedelta = datetime.timedelta(seconds=30)
    _supreme_signal_handler: SupremeSignalHandler

    def __init__(self, *args, **kwargs) -> None:
        self._supreme_signal_handler = SupremeSignalHandler(
            context=kwargs['context'],
        )

        super().__init__(*args, **kwargs)

        now = datetime.datetime.now()

        self.task_queue.put(
            self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        )

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {
            **super().get_initial_state(),
            **self._supreme_signal_handler.get_initial_state(),
        }

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=lambda: tuple(self._compress_db()),
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=30),
                run_immediately=False,
            ),
            IntervalTask(
                target=lambda: Signal.backup(
                    datetime_range=(
                        get_current_time() - datetime.timedelta(days=1),
                        get_current_time(),
                    ),
                ),
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(hours=2),
                run_immediately=False,
            ),
            ScheduledTask(
                target=Signal.backup,
                priority=TaskPriorities.LOW,
                crontab=CronTab('0 5 * * *'),
            ),
            *self._supreme_signal_handler.get_tasks(),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_task_queue_stats),
            *self._supreme_signal_handler.subscribe_to_events(),
        )

    def disable(self) -> None:
        super().disable()
        self._supreme_signal_handler.disable()

    @interface.command(constants.BotCommands.COMPRESS_DB)
    def _compress_db_with_progress_bar(self) -> typing.Any:
        with ProgressBar(self.messenger, title='Checking DB\\.\\.\\.') as progress_bar:
            for progress in self._compress_db():
                progress_bar.set(progress)

            self.messenger.send_message('Compressing of DB is finished')

    def _ping_task_queue(self, *, sent_at: datetime.datetime) -> None:
        now = datetime.datetime.now()
        diff = datetime.datetime.now() - sent_at - self._timedelta_for_ping
        Signal.add(signal_type=constants.TASK_QUEUE_DELAY, value=diff.total_seconds(), received_at=now)

        now = datetime.datetime.now()

        self.task_queue.put(
            self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        )

    @staticmethod
    def _create_task_queue_stats(
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> io.BytesIO | None:
        if 'inner_stats' not in components:
            return None

        task_queue_size_stats = Signal.get(
            signal_type=constants.TASK_QUEUE_DELAY,
            datetime_range=date_range,
        )

        if not task_queue_size_stats:
            return None

        return create_plot(
            title='Task queue delay stats (sec.)',
            x_attr='received_at',
            y_attr='value',
            stats=task_queue_size_stats,
        )

    def _compress_db(self) -> typing.Generator:
        Signal.remove_old()

        for progress in self._supreme_signal_handler.compress():
            yield progress * 0.8

        now = get_current_time()

        with db.session_transaction() as session:
            session.query(Signal).filter(
                Signal.type == constants.TASK_QUEUE_DELAY,
                Signal.received_at <= now - datetime.timedelta(days=2),
            ).delete()

        datetime_range = (
            now - datetime.timedelta(hours=3),
            now - datetime.timedelta(minutes=5),
        )

        Signal.compress(
            constants.TASK_QUEUE_DELAY,
            datetime_range=datetime_range,
            approximation_time=datetime.timedelta(minutes=10),
        )

        yield 1
