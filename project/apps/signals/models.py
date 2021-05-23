import datetime
import typing

import sqlalchemy
from pandas import DataFrame
from sqlalchemy import DateTime, func as sa_func

from ... import config
from .. import db
from ..common.storage import file_storage
from ..db import db_session


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
        sqlalchemy.DateTime,
        index=True,
        nullable=False,
    )

    @classmethod
    def add(cls, signal_type: str, value: float, *, received_at: typing.Optional[datetime.datetime] = None) -> 'Signal':
        if received_at is None:
            received_at = datetime.datetime.now()

        item = cls(type=signal_type, value=value, received_at=received_at)

        with db.db_session().transaction:
            db.db_session().add(item)

        return item

    @classmethod
    def bulk_add(cls, signals: typing.Iterable['Signal']) -> None:
        with db.db_session().transaction:
            db.db_session().add_all(signals)

    @classmethod
    def clear(cls, signal_types: typing.Iterable[str]) -> None:
        timestamp = datetime.datetime.now() - config.STORAGE_TIME

        with db.db_session().transaction:
            db.db_session().query(cls).filter(cls.type.in_(signal_types), cls.received_at <= timestamp).delete()

    @classmethod
    def get(cls,
            signal_type: str, *,
            date_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            date_range=date_range,
        )

        if not query_data:
            return []

        signal = db.db_session().query(
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

        return signal

    @classmethod
    def get_aggregated(cls,
                       signal_type: str, *,
                       aggregate_function: typing.Callable = sa_func.avg,
                       date_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            date_range=date_range,
        )

        if not query_data:
            return []

        signals = db.db_session().query(
            aggregate_function(cls.value).label('value'),
            cls.received_at.label('received_at'),
            sa_func.datetime(
                sa_func.strftime(query_data['time_tpl'], cls.received_at),
                type_=DateTime,
            ).label('aggregated_time'),
        ).filter(
            cls.received_at >= query_data['start_time'],
            cls.received_at <= query_data['end_time'],
            cls.type == signal_type,
            cls.value.isnot(None),
        ).group_by(
            'aggregated_time',
        ).order_by(
            cls.received_at,
        ).all()

        return signals

    @classmethod
    def last_aggregated(cls,
                        signal_type: str, *,
                        aggregate_function: typing.Callable = sa_func.avg,
                        td: datetime.timedelta = datetime.timedelta(minutes=1)) -> typing.Any:
        now = datetime.datetime.now()

        result = db.db_session().query(
            aggregate_function(cls.value).label('value'),
        ).filter(
            cls.type == signal_type,
            cls.received_at >= now - td,
            cls.value.isnot(None),
        ).group_by().first()

        return result[0] if result else None

    @classmethod
    def compress(cls,
                 signal_type: str, *,
                 date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                 approximation: float = 0) -> None:
        data = cls.get(signal_type, date_range=date_range)

        if not data:
            return

        received_at_to_remove = []
        last_value_to_remove = None

        for i, item in enumerate(data):
            if i == 0 or i >= len(data) - 1:
                continue

            cond_1 = abs(data[i - 1].value - item.value) <= approximation
            cond_2 = abs(data[i + 1].value - item.value) <= approximation

            if last_value_to_remove is None:
                cond_3 = True
            else:
                cond_3 = abs(last_value_to_remove - item.value) <= approximation

            if cond_1 and cond_2 and cond_3:
                received_at_to_remove.append(item.received_at)

                if last_value_to_remove is None:
                    last_value_to_remove = item.value
            else:
                last_value_to_remove = None

        if received_at_to_remove:
            with db.db_session().transaction:
                db.db_session().query(cls).filter(
                    cls.type == signal_type,
                    cls.received_at.in_(received_at_to_remove),
                ).delete()

    @classmethod
    def aggregated_compress(cls,
                            signal_type: str, *,
                            aggregate_function: typing.Callable = sa_func.avg,
                            date_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> None:
        aggregated_data = cls.get_aggregated(signal_type, aggregate_function=aggregate_function, date_range=date_range)

        start_time, end_time = date_range

        query = db.db_session().query(cls).filter(
            cls.received_at >= start_time,
            cls.received_at <= end_time,
            cls.type == signal_type,
        )

        count = query.count()

        if not count or len(aggregated_data) / count > 0.9:
            return

        with db.db_session().transaction:
            query.delete()

            db.db_session().add_all(
                cls(
                    type=signal_type,
                    value=item.value,
                    received_at=item.received_at,
                )
                for item in aggregated_data
            )

    @classmethod
    def backup(cls) -> None:
        all_data = db_session().query(
            cls.type,
            cls.value,
            cls.received_at,
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
                        date_range: typing.Tuple[datetime.datetime, datetime.datetime],
                        ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        start_time, end_time = date_range

        time_filter = db.db_session().query(cls.received_at).filter(
            cls.received_at >= start_time,
            cls.received_at <= end_time,
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
            time_tpl = '%Y-%m-%dT%H:%M:%S'
        else:
            time_tpl = '%Y-%m-%dT%H:%M:00'

        return {
            'time_tpl': time_tpl,
            'start_time': first_time,
            'end_time': last_time,
        }
