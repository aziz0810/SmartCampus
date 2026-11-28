from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_engine():
    """Check connectivity once so unreachable-DB skips stay fast and clear."""
    try:
        from app.config import settings

        engine = create_engine(
            settings.database_url,
            connect_args={"connect_timeout": 3},
        )
    except Exception as exc:
        pytest.skip(f"PostgreSQL test database is not configured: {type(exc).__name__}")

    try:
        with engine.connect():
            pass
    except SQLAlchemyError as exc:
        engine.dispose()
        detail = str(getattr(exc, "orig", exc)).splitlines()[0]
        pytest.skip(
            f"PostgreSQL test database is unreachable: {type(exc).__name__}: {detail}"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_schema(postgres_engine) -> Iterator[tuple[Connection, Config]]:
    """Create and migrate an isolated schema inside one rolled-back transaction."""
    connection = postgres_engine.connect()
    transaction = connection.begin()
    schema_name = f"test_sa17_{uuid4().hex}"
    try:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield connection, config
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()
