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
        return db.get_db_session().query(
            cls.name,
            cls.value,
        ).all()

    @classmethod
    def set(cls, name: str, value: typing.Any) -> None:
        with db.session_transaction() as session:
            if session.query(cls).filter(cls.name == name).first() is None:
                session.add(cls(name=name, value=value))
            else:
                session.query(cls).filter(cls.name == name).update({cls.value: value})

    @classmethod
    def delete(cls, name: str) -> None:
        with db.session_transaction() as session:
            session.query(cls).filter(cls.name == name).delete()
