import datetime
import typing

import sqlalchemy
from sqlalchemy import func

from .. import db
from ... import config


class Signal(db.Base):
    __tablename__ = 'signals'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    type = sqlalchemy.Column(sqlalchemy.Text)
    value = sqlalchemy.Column(sqlalchemy.Float)
    received_at = sqlalchemy.Column(sqlalchemy.DateTime, index=True)

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
    def get(cls, signal_type: str, *, date_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            date_range=date_range,
        )

        if not query_data:
            return []

        signal = db.db_session().query(
            cls.value,
            cls.received_at.label('time'),
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
                       aggregate_function: typing.Callable,
                       date_range: typing.Tuple[datetime.datetime, datetime.datetime]) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            date_range=date_range,
        )

        if not query_data:
            return []

        signals = db.db_session().query(
            aggregate_function(cls.value).label('value'),
            cls.received_at.label('time'),
            func.strftime(query_data['time_tpl'], cls.received_at).label('aggregated_time'),
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
            time_tpl = '%m.%d %H:%M:%S'
        else:
            time_tpl = '%m.%d %H:%M'

        return {
            'time_tpl': time_tpl,
            'start_time': first_time,
            'end_time': last_time,
        }
