import datetime
import io
import typing

from ...common import utils
from ...common.constants import NOTHING
from ...signals.models import Signal
from .. import constants
from .base import BaseSimpleSignalHandler, NotificationParams


class CpuTempHandler(BaseSimpleSignalHandler):
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
            return utils.get_cpu_temp()
        except RuntimeError:
            return NOTHING

    def generate_plots(
        self,
        *,
        date_range: tuple[datetime.datetime, datetime.datetime],
        components: set[str],
    ) -> typing.Sequence[io.BytesIO] | None:
        if 'inner_stats' not in components:
            return None

        cpu_temp_stats = Signal.get_aggregated(
            signal_type=constants.CPU_TEMPERATURE,
            datetime_range=date_range,
        )

        if not cpu_temp_stats:
            return None

        return (
            utils.create_plot(
                title='CPU temperature',
                x_attr='aggregated_time',
                y_attr='value',
                stats=cpu_temp_stats,
            ),
        )
