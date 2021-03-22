import datetime
import typing


__all__ = (
    'BaseTaskQueueException',
    'RepeatTask',
)


class BaseTaskQueueException(Exception):
    pass


class RepeatTask(BaseTaskQueueException):
    after: typing.Optional[datetime.timedelta]
    source: typing.Optional[Exception]

    def __init__(self, *,
                 after: typing.Optional[datetime.timedelta] = None,
                 source: typing.Optional[Exception]) -> None:
        self.after = after
        self.source = source
