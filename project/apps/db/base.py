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
db_engine = create_engine(
    config.DATABASE_URL,
    isolation_level='READ COMMITTED',
    echo=config.DATABASE_DEBUG,
)

session_factory = sessionmaker(bind=db_engine, autocommit=True)
MySession = scoped_session(session_factory)


def db_session() -> Session:
    return MySession()


close_db_session = MySession.remove


def vacuum() -> None:
    with db_engine.connect() as con:
        con.execution_options(isolation_level='AUTOCOMMIT').execute('VACUUM FULL;')


def clear_db() -> None:
    with db_engine.connect() as con:
        con.execute('SELECT \'drop table if exists '' || tablename || '" cascade;' FROM pg_tables;")
