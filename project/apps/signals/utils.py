import datetime
import itertools
import typing

from .models import Signal


# def downgrade_signals(signals: typing.Sequence[Signal]) -> typing.Generator[Signal, None, None]:
#     if len(signals) < 2:
#         yield from signals
#
#     if (signals[-1].received_at - signals[0].received_at) < datetime.timedelta(minutes=2):
#         one_time_item = datetime.timedelta(seconds=1)
#     else:
#         one_time_item = datetime.timedelta(minutes=1)
#
#     one_microsecond = datetime.timedelta(microseconds=1)
#
#     yield signals[0]
#
#     previous_time = signals[0].received_at
#
#     for signal in itertools.islice(signals, 1, None):
#         if signal.received_at - previous_time > one_time_item:
#             yield Signal(
#                 value=0,
#                 received_at=previous_time + one_microsecond,
#             )
#             yield Signal(
#                 value=0,
#                 received_at=signal.received_at - one_microsecond,
#             )
#
#         yield Signal(value=signal.value, received_at=signal.received_at)
#
#         previous_time = signal.received_at
