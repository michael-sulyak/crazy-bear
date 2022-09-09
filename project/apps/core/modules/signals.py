import datetime
import typing

from crontab import CronTab

from .. import constants, events
from ..base import BaseModule, Command
from ..utils.signal_handlers import SupremeSignalHandler
from ... import db
from ...arduino.constants import ArduinoSensorTypes
from ...common import doc
from ...common.utils import current_time, create_plot
from ...messengers.utils import ProgressBar
from ...signals.models import Signal
from ...task_queue import IntervalTask, ScheduledTask, TaskPriorities


__all__ = (
    'Signals',
)


class Signals(BaseModule):
    doc = doc.generate_doc(
        title='Signals',
        commands=(
            doc.CommandDef(constants.BotCommands.CHECK_DB),
        ),
    )
    _timedelta_for_ping: datetime.timedelta = datetime.timedelta(seconds=30)
    _supreme_signal_handler: SupremeSignalHandler

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._supreme_signal_handler = SupremeSignalHandler(messenger=self.messenger)

        now = datetime.datetime.now()

        self.task_queue.put(
            self._ping_task_queue,
            kwargs={'sent_at': now},
            priority=TaskPriorities.LOW,
            run_after=now + self._timedelta_for_ping,
        )

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._check_db,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=30),
                run_immediately=False,
            ),
            IntervalTask(
                target=lambda: Signal.backup(
                    datetime_range=(
                        current_time() - datetime.timedelta(days=1),
                        current_time(),
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
            ScheduledTask(
                target=db.vacuum,
                priority=TaskPriorities.LOW,
                crontab=CronTab('0 4 * * *'),
            ),
            *self._supreme_signal_handler.get_tasks(),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.request_for_statistics.connect(self._create_task_queue_stats),
            events.request_for_statistics.connect(self._create_weather_stats),
            *self._supreme_signal_handler.get_signals(),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == constants.BotCommands.CHECK_DB:
            with ProgressBar(self.messenger, title='Checking DB\\.\\.\\.') as progress_bar:
                self._check_db()
                progress_bar.set(0.5, title='Run `VACUUM FULL`\\.\\.\\.')
                db.vacuum()
                progress_bar.set(1)
                self.messenger.send_message('Checking DB is finished')

            return True

        return False

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
    def _create_task_queue_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                                 components: typing.Set[str]) -> typing.Optional[io.BytesIO]:
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

    @staticmethod
    def _create_weather_stats(date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                              components: typing.Set[str]) -> typing.Optional[typing.List[io.BytesIO]]:
        if 'arduino' not in components:
            return None

        humidity_stats = Signal.get_aggregated(ArduinoSensorTypes.HUMIDITY, datetime_range=date_range)
        temperature_stats = Signal.get_aggregated(ArduinoSensorTypes.TEMPERATURE, datetime_range=date_range)

        weather_temperature = None
        weather_humidity = None

        if 'extra_data' in components:
            if len(temperature_stats) >= 2:
                weather_humidity = Signal.get_aggregated(
                    signal_type=constants.WEATHER_HUMIDITY,
                    datetime_range=(humidity_stats[0].aggregated_time, humidity_stats[-1].aggregated_time,),
                )

            if len(temperature_stats) >= 2:
                weather_temperature = Signal.get_aggregated(
                    signal_type=constants.WEATHER_TEMPERATURE,
                    datetime_range=(temperature_stats[0].aggregated_time, temperature_stats[-1].aggregated_time,),
                )

        plots = []

        if temperature_stats:
            plots.append(create_plot(
                title='Temperature',
                x_attr='aggregated_time',
                y_attr='value',
                stats=temperature_stats,
                additional_plots=(
                    ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_temperature},)
                    if weather_temperature else None
                ),
                legend=(
                    ('Inside', 'Outside',)
                    if weather_temperature else None
                ),
            ))

        if humidity_stats:
            plots.append(create_plot(
                title='Humidity',
                x_attr='aggregated_time',
                y_attr='value',
                stats=humidity_stats,
                additional_plots=(
                    ({'x_attr': 'aggregated_time', 'y_attr': 'value', 'stats': weather_humidity},)
                    if weather_humidity else None
                ),
                legend=(
                    ('Inside', 'Outside',)
                    if weather_humidity else None
                ),
            ))

        pir_stats = Signal.get(ArduinoSensorTypes.PIR_SENSOR, datetime_range=date_range)

        if pir_stats:
            plots.append(create_plot(title='PIR Sensor', x_attr='received_at', y_attr='value', stats=pir_stats))

        return plots

    def _check_db(self) -> None:
        self._supreme_signal_handler.compress()

        now = current_time()

        for_compress = (
            constants.USER_IS_CONNECTED_TO_ROUTER,
            constants.TASK_QUEUE_DELAY,
            ArduinoSensorTypes.PIR_SENSOR,
        )

        for_compress_by_time = (
            ArduinoSensorTypes.TEMPERATURE,
            ArduinoSensorTypes.HUMIDITY,
        )

        all_signals = {*for_compress, *for_compress_by_time}

        Signal.clear(all_signals)

        with db.db_session().begin():
            db.db_session().query(Signal).filter(
                Signal.type == constants.TASK_QUEUE_DELAY,
                Signal.received_at <= now - datetime.timedelta(days=2),
            ).delete()

        datetime_range = (
            now - datetime.timedelta(hours=3),
            now - datetime.timedelta(minutes=5),
        )

        for item in for_compress:
            if item == ArduinoSensorTypes.PIR_SENSOR:
                approximation_value = 20
            elif item in (ArduinoSensorTypes.TEMPERATURE, ArduinoSensorTypes.HUMIDITY,):
                approximation_value = 0.1
            else:
                approximation_value = 0

            Signal.compress(
                item,
                datetime_range=datetime_range,
                approximation_value=approximation_value,
                approximation_time=datetime.timedelta(minutes=10),
            )

        for item in for_compress_by_time:
            Signal.compress_by_time(
                item,
                datetime_range=datetime_range,
            )

            Signal.compress(
                item,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )

        # TODO: Figure out how to clean old signals
        # db.db_session().query(Signal).filter(
        #     Signal.type.notin_(all_signals),
        # ).delete()
