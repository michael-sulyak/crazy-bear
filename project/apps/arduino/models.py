import datetime
import typing

import sqlalchemy
from sqlalchemy import func

from .. import db
from ... import config


class ArduinoLog(db.Base):
    __tablename__ = 'arduino_logs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    pir_sensor = sqlalchemy.Column(sqlalchemy.Float)
    humidity = sqlalchemy.Column(sqlalchemy.Float)
    temperature = sqlalchemy.Column(sqlalchemy.Float)
    received_at = sqlalchemy.Column(sqlalchemy.DateTime)

    @classmethod
    def last_avg(cls) -> typing.Any:
        now = datetime.datetime.now()

        return db.db_session().query(
            func.avg(cls.humidity).label('humidity'),
            func.avg(cls.pir_sensor).label('pir_sensor'),
            func.avg(cls.temperature).label('temperature'),
        ).filter(
            cls.received_at >= now - datetime.timedelta(minutes=1),
            cls.humidity.isnot(None),
            cls.pir_sensor.isnot(None),
            cls.temperature.isnot(None),
        ).group_by().first()

    @classmethod
    def get_avg(cls, delta_type: str = 'hours', delta_value: int = 24) -> typing.List['ArduinoLog']:
        start_time = datetime.datetime.now() - datetime.timedelta(**{delta_type: delta_value})

        time_filter = db.db_session().query(cls.received_at).filter(
            cls.received_at >= start_time,
            cls.humidity.isnot(None),
            cls.pir_sensor.isnot(None),
            cls.temperature.isnot(None),
        )
        first_time = time_filter.order_by(cls.received_at).first()
        last_time = time_filter.order_by(cls.received_at.desc()).first()

        if not first_time or not last_time:
            return []

        diff = last_time[0] - first_time[0]

        if diff < datetime.timedelta(minutes=2):
            time_tpl = '%y.%m.%d %H:%M:%S'
        else:
            time_tpl = '%y.%m.%d %H:%M'

        signals = db.db_session().query(
            func.avg(cls.humidity).label('humidity'),
            func.avg(cls.pir_sensor).label('pir_sensor'),
            func.avg(cls.temperature).label('temperature'),
            cls.received_at.label('time'),
            func.strftime(time_tpl, cls.received_at).label('avg_time'),
        ).filter(
            cls.received_at >= start_time,
            cls.humidity.isnot(None),
            cls.pir_sensor.isnot(None),
            cls.temperature.isnot(None),
        ).group_by(
            'time',
        ).order_by(
            cls.received_at,
        ).all()

        return signals

    @classmethod
    def clear(cls) -> None:
        timestamp = datetime.datetime.now() - config.STORAGE_TIME

        with db.db_session().transaction:
            db.db_session().query(cls).filter(cls.received_at <= timestamp).delete()
