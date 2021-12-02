__all__ = (
    'TaskPriorities',
    'TaskStatus',
)


class TaskPriorities:
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatus:
    CREATED = 'created'
    PENDING = 'pending'
    STARTED = 'started'
    FINISHED = 'finished'
    FAILED = 'failed'
    CANCELED = 'canceled'
