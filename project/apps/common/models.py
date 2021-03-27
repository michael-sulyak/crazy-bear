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
    received_at = sqlalchemy.Column(sqlalchemy.DateTime)

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
    def get(cls, signal_type: str, *, delta_type: str = 'hours', delta_value: int = 24) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            delta_type=delta_type,
            delta_value=delta_value,
        )

        if not query_data:
            return []

        signal = db.db_session().query(
            cls.value,
            cls.received_at.label('time'),
        ).filter(
            cls.received_at >= query_data['start_time'],
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
                       delta_type: str = 'hours',
                       delta_value: int = 24) -> typing.List['Signal']:
        query_data = cls._get_query_data(
            signal_type=signal_type,
            delta_type=delta_type,
            delta_value=delta_value,
        )

        if not query_data:
            return []

        signal = db.db_session().query(
            aggregate_function(cls.value).label('value'),
            cls.received_at.label('time'),
            func.strftime(query_data['time_tpl'], cls.received_at).label('aggregated_time'),
        ).filter(
            cls.received_at >= query_data['start_time'],
            cls.type == signal_type,
            cls.value.isnot(None),
        ).group_by(
            'aggregated_time',
        ).order_by(
            cls.received_at,
        ).all()

        return signal

    @classmethod
    def _get_query_data(cls,
                        signal_type: str, *,
                        delta_type: str = 'hours',
                        delta_value: int = 24) -> typing.Optional[typing.Dict[str, typing.Any]]:
        start_time = datetime.datetime.now() - datetime.timedelta(**{delta_type: delta_value})

        time_filter = db.db_session().query(cls.received_at).filter(
            cls.received_at >= start_time,
            cls.type == signal_type,
            cls.value.isnot(None),
        )
        first_time = time_filter.order_by(cls.received_at).first()
        last_time = time_filter.order_by(cls.received_at.desc()).first()

        if not first_time or not last_time:
            return None

        diff = last_time[0] - first_time[0]

        if diff < datetime.timedelta(minutes=2):
            time_tpl = '%m.%d %H:%M:%S'
        else:
            time_tpl = '%m.%d %H:%M'

        return {
            'time_tpl': time_tpl,
            'start_time': start_time,
        }
