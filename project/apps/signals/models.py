import datetime
import typing

import sqlalchemy
from pandas import DataFrame
from sqlalchemy import func as sa_func

from .. import db
from ..common.storage import file_storage
from ..common.utils import current_time
from ..db import db_session
from ... import config


class Signal(db.Base):
    __tablename__ = 'signals'

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
    )
    type = sqlalchemy.Column(
        sqlalchemy.Text,
        index=True,
        nullable=False,
    )
    value = sqlalchemy.Column(
        sqlalchemy.Float,
        nullable=False,
    )
    received_at = sqlalchemy.Column(
        sqlalchemy.DateTime(timezone=True),
        index=True,
        nullable=False,
    )

    @classmethod
    def add(cls, signal_type: str, value: float, *, received_at: typing.Optional[datetime.datetime] = None) -> 'Signal':
        if received_at is None:
            received_at = current_time()

        item = cls(type=signal_type, value=value, received_at=received_at)

        with db.db_session().begin():
            db.db_session().add(item)

        return item

    @classmethod
    def bulk_add(cls, signals: typing.Iterable['Signal']) -> None:
        with db.db_session().begin():
            db.db_session().add_all(signals)

    @classmethod
    def clear(cls, signal_types: typing.Iterable[str]) -> None:
        timestamp = current_time() - config.STORAGE_TIME

        with db.db_session().begin():
            db.db_session().query(cls).filter(cls.type.in_(signal_types), cls.received_at <= timestamp).delete()

    @classmethod
    def get(cls,
            signal_type: str, *,
            datetime_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            datetime_range=datetime_range,
        )

        if not query_data:
            return []

        signals = db.db_session().query(
            cls.value,
            cls.received_at.label('received_at'),
        ).filter(
            cls.received_at >= query_data['start_time'],
            cls.received_at <= query_data['end_time'],
            cls.type == signal_type,
            cls.value.isnot(None),
        ).order_by(
            cls.received_at,
        ).all()

        return signals

    @classmethod
    def get_aggregated(cls,
                       signal_type: str, *,
                       aggregate_function: typing.Callable = sa_func.avg,
                       datetime_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            datetime_range=datetime_range,
        )

        if not query_data:
            return []

        signals = db.db_session().query(
            aggregate_function(cls.value).label('value'),
            sa_func.date_trunc(query_data['date_trunc'], cls.received_at).label('aggregated_time'),
        ).filter(
            cls.received_at >= query_data['start_time'],
            cls.received_at <= query_data['end_time'],
            cls.type == signal_type,
            cls.value.isnot(None),
        ).group_by(
            'aggregated_time',
        ).order_by(
            'aggregated_time',
        ).all()

        return signals

    @classmethod
    def last_aggregated(cls,
                        signal_type: str, *,
                        aggregate_function: typing.Callable = sa_func.avg,
                        td: datetime.timedelta = datetime.timedelta(minutes=1)) -> typing.Any:
        now = current_time()

        result = db.db_session().query(
            aggregate_function(cls.value).label('value'),
        ).filter(
            cls.type == signal_type,
            cls.received_at >= now - td,
            cls.value.isnot(None),
        ).first()[0]

        return result

    @classmethod
    def compress_by_time(cls,
                         signal_type: str, *,
                         datetime_range: typing.Tuple[datetime.datetime, datetime.datetime],
                         aggregate_function: typing.Callable = sa_func.avg) -> None:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            datetime_range=datetime_range,
        )

        if not query_data:
            return

        signals = db.db_session().query(
            aggregate_function(cls.value).label('aggregated_value'),
            sa_func.date_trunc(query_data['date_trunc'], cls.received_at).label('aggregated_time'),
        ).filter(
            cls.received_at >= query_data['start_time'],
            cls.received_at <= query_data['end_time'],
            cls.type == signal_type,
            cls.value.isnot(None),
        ).group_by(
            'aggregated_time',
        ).order_by(
            'aggregated_time',
        ).all()

        if not signals:
            return

        new_signals = tuple(
            Signal(type=signal_type, value=signal.aggregated_value, received_at=signal.aggregated_time)
            for signal in signals
        )

        with db.db_session().begin():
            db.db_session().query(cls).filter(
                cls.received_at >= query_data['start_time'],
                cls.received_at <= query_data['end_time'],
                cls.type == signal_type,
            ).delete()
            db.db_session().add_all(new_signals)

    @classmethod
    def compress(cls,
                 signal_type: str, *,
                 datetime_range: typing.Tuple[datetime.datetime, datetime.datetime],
                 approximation_value: float = 0,
                 approximation_time: datetime.timedelta = datetime.timedelta(hours=1)) -> None:
        signals = cls.get(signal_type, datetime_range=datetime_range)

        if len(signals) < 2:
            return

        received_at_to_remove = []
        last_saved_value = signals[0]

        for i, item in enumerate(signals):
            if not (0 < i < len(signals) - 1):
                continue

            cond_1 = signals[i].received_at - last_saved_value.received_at <= approximation_time
            cond_2 = abs(item.value - last_saved_value.value) <= approximation_value
            cond_3 = abs(signals[i + 1].value - item.value) <= approximation_value

            if cond_1 and cond_2 and cond_3:
                received_at_to_remove.append(item.received_at)
            else:
                last_saved_value = signals[i]

        if received_at_to_remove:
            with db.db_session().begin():
                db.db_session().query(cls).filter(
                    cls.type == signal_type,
                    cls.received_at.in_(received_at_to_remove),
                ).delete()

    @classmethod
    def aggregated_compress(cls,
                            signal_type: str, *,
                            aggregate_function: typing.Callable = sa_func.avg,
                            datetime_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> None:
        aggregated_data = cls.get_aggregated(
            signal_type,
            aggregate_function=aggregate_function,
            datetime_range=datetime_range,
        )

        start_time, end_time = datetime_range

        query = db.db_session().query(cls).filter(
            cls.received_at >= start_time,
            cls.received_at <= end_time,
            cls.type == signal_type,
        )

        count = query.count()

        if not count or len(aggregated_data) / count > 0.9:
            return

        with db.db_session().begin():
            query.delete()

            db.db_session().add_all(
                cls(
                    type=signal_type,
                    value=item.value,
                    received_at=item.aggregated_time,
                )
                for item in aggregated_data
            )

    @classmethod
    def backup(cls,
               datetime_range: typing.Optional[typing.Tuple[datetime.datetime, datetime.datetime]] = None) -> None:
        if datetime_range is None:
            filters = ()
        else:
            filters = (
                cls.received_at >= datetime_range[0],
                cls.received_at <= datetime_range[1],
            )

        all_data = db_session().query(
            cls.type,
            cls.value,
            cls.received_at,
        ).filter(
            *filters,
        ).order_by(
            cls.received_at,
        ).all()

        if not all_data:
            return

        df = DataFrame(all_data, columns=('type', 'value', 'received_at',))

        file_storage.upload_df_as_csv(
            file_name=f'signals/{df.iloc[0].received_at.strftime("%Y-%m-%d, %H:%M:%S")}'
                      f'-{df.iloc[-1].received_at.strftime("%Y-%m-%d, %H:%M:%S")}.csv',
            data_frame=df,
        )

    @classmethod
    def get_table_stats(cls) -> typing.Dict[str, int]:
        all_types = (
            item[0]
            for item in db.db_session().query(cls.type.distinct()).all()
        )

        return {
            item: db.db_session().query(cls).filter(cls.type == item).count()
            for item in all_types
        }

    @classmethod
    def _get_query_data(cls,
                        signal_type: str, *,
                        datetime_range: typing.Tuple[datetime.datetime, datetime.datetime],
                        ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        time_filter = db.db_session().query(
            cls.received_at,
        ).filter(
            cls.received_at >= datetime_range[0],
            cls.received_at <= datetime_range[1],
            cls.type == signal_type,
            cls.value.isnot(None),
        )
        first_time = time_filter.order_by(cls.received_at).first()
        last_time = time_filter.order_by(cls.received_at.desc()).first()

        if not first_time or not last_time:
            return None

        first_time, last_time = first_time[0], last_time[0]

        diff = last_time - first_time

        if diff < datetime.timedelta(minutes=2):
            date_trunc = 'second'
        else:
            date_trunc = 'minute'

        return {
            'date_trunc': date_trunc,
            'start_time': first_time,
            'end_time': last_time,
        }
