from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.orm.session import Session

from ... import config


__all__ = (
    'Base',
    'db_engine',
    'db_session',
    'close_db_session',
    'vacuum',
)

Base = declarative_base()
db_engine = create_engine(config.DATABASE_URL, echo=config.DATABASE_DEBUG)

session_factory = sessionmaker(bind=db_engine)
MySession = scoped_session(session_factory)


def db_session() -> Session:
    return MySession()


close_db_session = MySession.remove


def vacuum() -> None:
    with db_engine.connect() as con:
        con.execute('VACUUM;')
