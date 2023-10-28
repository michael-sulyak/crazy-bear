import contextlib
import typing

from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base, Session

from ... import config


__all__ = (
    'Base',
    'db_engine',
    'get_db_session',
    'close_db_session',
    'vacuum',
    'session_transaction',
    'transaction',
)

Base = declarative_base()
db_engine = create_engine(
    url=config.DATABASE_URL,
    isolation_level='READ COMMITTED',
    echo=config.DATABASE_DEBUG,
    connect_args={'connect_timeout': 60},
)

session_factory = sessionmaker(bind=db_engine, autoflush=True, expire_on_commit=False)
MySession = scoped_session(session_factory)


def get_db_session() -> Session:
    return MySession()


@contextlib.contextmanager
def session_transaction() -> typing.Generator:
    with get_db_session() as session, transaction(session):
        yield session


@contextlib.contextmanager
def transaction(session) -> typing.Generator:
    with session.begin_nested():
        try:
            yield
        except Exception as e:
            raise e
        else:
            session.commit()


close_db_session = MySession.remove


def vacuum() -> None:
    with db_engine.connect() as connection:
        connection.execution_options(isolation_level='AUTOCOMMIT').execute(text('VACUUM FULL;'))
