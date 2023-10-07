import datetime
import io
import typing

from .base import BaseAdvancedSignalHandler, NotificationParams
from .. import constants
from ...common import utils
from ...signals.models import Signal


class FreeDiskSpaceHandler(BaseAdvancedSignalHandler):
    signal_type = constants.FREE_DISK_SPACE
    task_interval = datetime.timedelta(minutes=1)
    compress_by_time = True
    list_of_notification_params = (
        NotificationParams(
            condition=lambda x: x < 256,
            message='There is very little disk space left!',
            delay=datetime.timedelta(hours=1),
        ),
        NotificationParams(
            condition=lambda x: x < 512,
            message='There is little disk space left!',
            delay=datetime.timedelta(hours=6),
        ),
    )

    def get_value(self) -> typing.Any:
        return utils.get_free_disk_space()

    def generate_plots(self, *,
                       date_range: tuple[datetime.datetime, datetime.datetime],
                       components: typing.Set[str]) -> typing.Optional[typing.Sequence[io.BytesIO]]:
        if 'inner_stats' not in components:
            return None

        free_disk_space_stats = Signal.get_aggregated(
            signal_type=constants.FREE_DISK_SPACE,
            datetime_range=date_range,
        )

        if not free_disk_space_stats:
            return None

        return (
            utils.create_plot(
                title='Free disk space (MB)',
                x_attr='aggregated_time',
                y_attr='value',
                stats=free_disk_space_stats,
            ),
        )
