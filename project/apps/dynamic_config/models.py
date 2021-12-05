import typing

import sqlalchemy

from .. import db


class DynamicConstant(db.Base):
    __tablename__ = 'constants'

    name = sqlalchemy.Column(
        sqlalchemy.Text,
        primary_key=True,
    )
    value = sqlalchemy.Column(
        sqlalchemy.JSON,
        nullable=True,
    )

    @classmethod
    def all(cls) -> typing.List['DynamicConstant']:
        return db.db_session().query(
            cls.name,
            cls.value,
        ).all()

    @classmethod
    def set(cls, name: str, value: typing.Any) -> None:
        with db.db_session().begin():
            if db.db_session().query(cls).filter(cls.name == name).first() is None:
                db.db_session().add(cls(name=name, value=value))
            else:
                db.db_session().query(cls).filter(cls.name == name).update({cls.value: value})

    @classmethod
    def delete(cls, name: str) -> None:
        with db.db_session().begin():
            db.db_session().query(cls).filter(cls.name == name).delete()
