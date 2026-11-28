"""Shared helpers for the PostgreSQL integration tests (SA-12, SA-14).

The database comes from the root ``.env`` (or the environment inside the
backend container). Tests are skipped when it is unreachable.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import OperationalError

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR.parent / ".env"
DB_KEYS = ("DB_HOST", "DB_PORT", "APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD")


def _db_env() -> dict[str, str]:
    """The root .env wins, so placeholders set by other test modules
    (e.g. sqlite tests) cannot redirect these tests."""
    values = {key: os.environ[key] for key in DB_KEYS if key in os.environ}
    if ENV_FILE.exists():
        file_values = dotenv_values(ENV_FILE)
        values.update({k: v for k in DB_KEYS if (v := file_values.get(k))})
    return values


DB_ENV = _db_env()


def database_url() -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=DB_ENV.get("APP_DB_USER"),
        password=DB_ENV.get("APP_DB_PASSWORD"),
        host=DB_ENV.get("DB_HOST", "localhost"),
        port=int(DB_ENV.get("DB_PORT", "5432")),
        database=DB_ENV.get("APP_DB_NAME"),
    )


def run_alembic(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, **DB_ENV},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def connect_or_skip() -> Engine:
    if not all(DB_ENV.get(k) for k in ("APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD")):
        pytest.skip("PostgreSQL settings not configured")
    engine = create_engine(database_url(), connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError:
        engine.dispose()
        pytest.skip("PostgreSQL is not reachable")
    run_alembic("upgrade", "head")
    return engine


def non_empty_tables(engine: Engine) -> dict[str, int]:
    names = [n for n in inspect(engine).get_table_names() if n != "alembic_version"]
    with engine.connect() as connection:
        counts = {
            name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
            for name in names
        }
    return {name: count for name, count in counts.items() if count}


def downgrade_round_trip(engine: Engine, previous_revision: str, tables: tuple[str, ...]) -> None:
    """Downgrade to ``previous_revision``, check ``tables`` are gone, upgrade back.

    Downgrading may also drop tables of later migrations, so this only runs
    on a database with no rows at all.
    """
    data = non_empty_tables(engine)
    if data:
        pytest.skip(f"Database contains data, not downgrading: {data}")
    run_alembic("downgrade", previous_revision)
    try:
        assert set(inspect(engine).get_table_names()) & set(tables) == set()
    finally:
        run_alembic("upgrade", "head")
    assert set(tables) <= set(inspect(engine).get_table_names())
