import pytest
from sqlalchemy.orm import Session

from pg_helpers import connect_or_skip


@pytest.fixture(scope="module")
def engine():
    engine = connect_or_skip()
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """A session whose work is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
