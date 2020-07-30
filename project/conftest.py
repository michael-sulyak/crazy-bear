import pytest

from .apps import db


@pytest.fixture(scope='module')
def test_db():
    db.Base.metadata.create_all(db.db_engine)
