import datetime
import typing


__all__ = (
    'BaseTaskQueueException',
    'RepeatTask',
)


class BaseTaskQueueException(Exception):
    pass


class RepeatTask(BaseTaskQueueException):
    after: datetime.datetime
    source: typing.Optional[Exception]

    def __init__(
        self,
        *,
        after: typing.Optional[datetime.datetime] = None,
        delay: typing.Optional[datetime.timedelta] = None,
        source: typing.Optional[Exception] = None,
    ) -> None:
        if after is None:
            after = datetime.datetime.now()

        if delay is not None:
            after += delay

        self.after = after
        self.source = source
