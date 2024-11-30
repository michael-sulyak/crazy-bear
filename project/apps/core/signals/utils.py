import datetime

from libs.casual_utils.time import get_current_time


def get_default_signal_compress_datetime_range() -> tuple[datetime, datetime]:
    now = get_current_time()

    return (
        now - datetime.timedelta(hours=3),
        now - datetime.timedelta(minutes=5),
    )
