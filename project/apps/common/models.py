import datetime
import typing

import sqlalchemy
from sqlalchemy import func

from .. import db


class Signal(db.Base):
    __tablename__ = 'signals'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    type = sqlalchemy.Column(sqlalchemy.Text)
    value = sqlalchemy.Column(sqlalchemy.Float)
    received_at = sqlalchemy.Column(sqlalchemy.DateTime)

    @classmethod
    def add(cls, signal_type: str, value: float) -> 'Signal':
        item = cls(type=signal_type, value=value, received_at=datetime.datetime.now())
        db.db_session.add(item)
        db.db_session.commit()
        return item

    @classmethod
    def clear(cls, signal_type: str) -> None:
        day_ago = datetime.datetime.today() - datetime.timedelta(days=1)
        db.db_session.query(cls).filter(cls.type == signal_type, cls.received_at <= day_ago).delete()
        db.db_session.commit()

    @classmethod
    def get_avg(cls, signal_type: str, *, delta_type: str = 'hours', delta_value: int = 24) -> typing.List['Signal']:
        start_time = datetime.datetime.now() - datetime.timedelta(**{delta_type: delta_value})

        time_filter = db.db_session.query(cls.received_at).filter(
            cls.received_at >= start_time,
            cls.type == signal_type,
            cls.value.isnot(None),
        )
        first_time = time_filter.order_by(cls.received_at).first()
        last_time = time_filter.order_by(cls.received_at.desc()).first()

        if not first_time or not last_time:
            return []

        diff = last_time[0] - first_time[0]

        if diff < datetime.timedelta(minutes=2):
            time_tpl = '%H:%M:%S'
        else:
            time_tpl = '%H:%M'

        signal = db.db_session.query(
            func.avg(cls.value).label('value'),
            func.strftime(time_tpl, cls.received_at).label('time'),
            cls.value.isnot(None),
        ).filter(
            cls.received_at >= start_time,
            cls.type == signal_type,
        ).group_by(
            'time',
        ).order_by(
            cls.received_at,
        ).all()

        return signal
