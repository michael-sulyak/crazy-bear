__all__ = (
    'TaskPriorities',
    'TaskStatuses',
)


class TaskPriorities:
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatuses:
    CREATED = 'created'
    PENDING = 'pending'
    STARTED = 'started'
    FINISHED = 'finished'
    FAILED = 'failed'
    CANCELED = 'canceled'
