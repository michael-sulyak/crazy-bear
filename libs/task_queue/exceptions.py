import datetime


__all__ = (
    'BaseTaskQueueException',
    'RepeatTask',
)


class BaseTaskQueueException(Exception):
    pass


class RepeatTask(BaseTaskQueueException):
    after: datetime.datetime
    source: Exception | None

    def __init__(
        self,
        *,
        after: datetime.datetime | None = None,
        delay: datetime.timedelta | None = None,
        source: Exception | None = None,
    ) -> None:
        if after is None:
            after = datetime.datetime.now()

        if delay is not None:
            after += delay

        self.after = after
        self.source = source
