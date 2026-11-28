"""SA-12 integration tests: admission conditions and prerequisites on PostgreSQL.

Runs against the docker PostgreSQL configured in the root ``.env`` (or the
environment, inside the backend container). Skipped when it is unreachable.

Safety: inserted rows are demo rows (``is_demo=true``) inside a transaction
that is always rolled back. The downgrade/upgrade round trip only runs when
the SA-12 tables are empty, so it never deletes loaded data.
"""

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR.parent / ".env"
DB_KEYS = ("DB_HOST", "DB_PORT", "APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD")
SA12_TABLES = (
    "qualification",
    "admission_condition",
    "admission_condition_qualification",
    "formation_prerequisite",
    "subject_prerequisite",
)
PREVIOUS_REVISION = "9b20a2c83f71"
SOURCE_NOTE = "SA-12 test (fictional demo row)"


def _db_env() -> dict[str, str]:
    """Database settings: the root .env wins, so values set by other test
    modules (e.g. sqlite placeholders) cannot redirect this test."""
    values = {key: os.environ[key] for key in DB_KEYS if key in os.environ}
    if ENV_FILE.exists():
        file_values = dotenv_values(ENV_FILE)
        values.update({k: v for k in DB_KEYS if (v := file_values.get(k))})
    return values


DB_ENV = _db_env()


def _url() -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=DB_ENV.get("APP_DB_USER"),
        password=DB_ENV.get("APP_DB_PASSWORD"),
        host=DB_ENV.get("DB_HOST", "localhost"),
        port=int(DB_ENV.get("DB_PORT", "5432")),
        database=DB_ENV.get("APP_DB_NAME"),
    )


def _alembic(*args: str) -> None:
    env = {**os.environ, **DB_ENV}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def engine():
    if not all(DB_ENV.get(k) for k in ("APP_DB_NAME", "APP_DB_USER", "APP_DB_PASSWORD")):
        pytest.skip("PostgreSQL settings not configured")
    engine = create_engine(_url(), connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError:
        engine.dispose()
        pytest.skip("PostgreSQL is not reachable")
    _alembic("upgrade", "head")
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


def _catalog(db: Session):
    from app.models import Formation, Institution, Specialty, Subject

    institution = Institution(code="SA12-TEST", name="Institution de test SA-12")
    db.add(institution)
    db.flush()
    formation = Formation(
        institution_id=institution.id,
        code="sa12-ing-test",
        name="Cycle ingénieur (test)",
        kind="ingenieur",
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    db.add(formation)
    db.flush()
    specialty = Specialty(
        formation_id=formation.id,
        code="general",
        name="general",
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    algo = Subject(code="SA12-ALGO", name="Algorithmique (test)", is_demo=True)
    data = Subject(code="SA12-DS", name="Structures de données (test)", is_demo=True)
    db.add_all([specialty, algo, data])
    db.flush()
    return formation, specialty, algo, data


def test_tables_exist_after_upgrade(engine):
    tables = set(inspect(engine).get_table_names())
    assert set(SA12_TABLES) <= tables


def test_admission_condition_with_accepted_diplomas(session):
    from app.models import (
        AdmissionCondition,
        AdmissionConditionQualification,
        FormationPrerequisite,
        Qualification,
        SubjectPrerequisite,
    )

    formation, specialty, algo, data = _catalog(session)
    prepa = Qualification(
        code="sa12-prepa-mp",
        name="Diplôme du cycle préparatoire MP (test)",
        kind="prepa",
        field="MP",
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    licence = Qualification(
        code="sa12-lic-info",
        name="Licence en informatique (test)",
        kind="licence",
        field="informatique",
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    session.add_all([prepa, licence])
    session.flush()

    condition = AdmissionCondition(
        formation_id=formation.id,
        specialty_id=specialty.id,
        entry_year=1,
        route="prepa",
        min_average=Decimal("12.50"),
        academic_year="2026-2027",
        description="Accès en 1re année du cycle ingénieur après une prépa (test).",
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    session.add(condition)
    session.flush()
    session.add_all(
        [
            AdmissionConditionQualification(
                admission_condition_id=condition.id, qualification_id=q.id
            )
            for q in (prepa, licence)
        ]
    )
    session.add(
        FormationPrerequisite(
            formation_id=formation.id,
            description="Bases en mathématiques et en programmation (test).",
            is_demo=True,
            source_note=SOURCE_NOTE,
        )
    )
    session.add(SubjectPrerequisite(subject_id=data.id, required_subject_id=algo.id))
    session.flush()

    # "Can I get in with my licence?" is a lookup by qualification.
    accepted = session.scalars(
        select(AdmissionCondition.id)
        .join(AdmissionConditionQualification)
        .join(Qualification)
        .where(Qualification.code == "sa12-lic-info")
    ).all()
    assert accepted == [condition.id]

    row = session.get(AdmissionCondition, condition.id)
    assert row.is_demo is True
    assert row.created_at is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"route": "concours"},
        {"entry_year": 0},
        {"min_average": Decimal("20.50")},
    ],
    ids=["invalid-route", "entry-year-zero", "average-above-20"],
)
def test_admission_condition_checks(session, overrides):
    from app.models import AdmissionCondition

    formation, *_ = _catalog(session)
    values = {
        "formation_id": formation.id,
        "entry_year": 1,
        "route": "bac",
        "description": "Condition invalide (test).",
        "is_demo": True,
    } | overrides
    session.add(AdmissionCondition(**values))
    with pytest.raises(IntegrityError):
        session.flush()


def test_qualification_kind_and_code_are_checked(session):
    from app.models import Qualification

    session.add(Qualification(code="sa12-bad", name="Bad kind", kind="doctorat"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(Qualification(code="sa12-dup", name="A", kind="bac", is_demo=True))
    session.flush()
    session.add(Qualification(code="sa12-dup", name="B", kind="bac", is_demo=True))
    with pytest.raises(IntegrityError):
        session.flush()


def test_subject_cannot_require_itself(session):
    from app.models import SubjectPrerequisite

    _, _, algo, _ = _catalog(session)
    session.add(SubjectPrerequisite(subject_id=algo.id, required_subject_id=algo.id))
    with pytest.raises(IntegrityError):
        session.flush()


def test_formation_with_admission_conditions_cannot_be_deleted(session):
    from app.models import AdmissionCondition

    formation, specialty, *_ = _catalog(session)
    session.add(
        AdmissionCondition(
            formation_id=formation.id,
            entry_year=1,
            route="bac",
            description="Condition (test).",
            is_demo=True,
        )
    )
    session.delete(specialty)  # leave only the admission FK pointing at it
    session.flush()
    session.delete(formation)
    with pytest.raises(IntegrityError, match="fk_admission_condition_formation_id_formation"):
        session.flush()


def test_downgrade_then_upgrade(engine):
    with engine.connect() as connection:
        counts = {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in SA12_TABLES
        }
    if any(counts.values()):
        pytest.skip(f"SA-12 tables contain data, not downgrading: {counts}")

    _alembic("downgrade", PREVIOUS_REVISION)
    try:
        remaining = set(inspect(engine).get_table_names()) & set(SA12_TABLES)
        assert remaining == set()
    finally:
        _alembic("upgrade", "head")
    assert set(SA12_TABLES) <= set(inspect(engine).get_table_names())
