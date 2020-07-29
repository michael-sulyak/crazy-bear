from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from project import config


__all__ = (
    'Base',
    'db_engine',
    'db_session',
)

Base = declarative_base()
db_engine = create_engine(config.DATABASE_URL, echo=config.DATABASE_DEBUG)

Session = sessionmaker(bind=db_engine)
db_session = Session()
