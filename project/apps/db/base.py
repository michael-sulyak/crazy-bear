import contextlib
import typing

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base, Session

from ... import config


__all__ = (
    'Base',
    'db_engine',
    'get_db_session',
    'close_db_session',
    'vacuum',
    'session_transaction',
)

Base = declarative_base()
db_engine = create_engine(
    config.DATABASE_URL,
    isolation_level='READ COMMITTED',
    echo=config.DATABASE_DEBUG,
)

session_factory = sessionmaker(bind=db_engine, autoflush=True, expire_on_commit=False)
MySession = scoped_session(session_factory)


def get_db_session() -> Session:
    return MySession()


@contextlib.contextmanager
def session_transaction() -> typing.Generator:
    with get_db_session() as session, session.begin():
        yield session


close_db_session = MySession.remove


def vacuum() -> None:
    with db_engine.connect() as con:
        con.execution_options(isolation_level='AUTOCOMMIT').execute('VACUUM FULL;')


def clear_db() -> None:
    with db_engine.connect() as con:
        con.execute('SELECT \'drop table if exists '' || tablename || '" cascade;' FROM pg_tables;")
