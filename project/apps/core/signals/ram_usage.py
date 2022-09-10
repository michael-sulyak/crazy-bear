import datetime
import io
import typing

from .base import BaseAdvancedSignalHandler, NotificationParams
from .. import constants
from ...common import utils
from ...signals.models import Signal


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
        return round(utils.get_ram_usage() * 100, 2)

    def create_plots(self, *,
                     date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                     components: typing.Set[str]) -> typing.Optional[typing.Sequence[io.BytesIO]]:
        if 'inner_stats' not in components:
            return None

        ram_stats = Signal.get_aggregated(
            signal_type=constants.RAM_USAGE,
            datetime_range=date_range,
        )

        if not ram_stats:
            return None

        return (
            utils.create_plot(
                title='RAM usage (%)',
                x_attr='aggregated_time',
                y_attr='value',
                stats=ram_stats,
            ),
        )
