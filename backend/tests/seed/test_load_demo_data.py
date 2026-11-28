from secrets import token_urlsafe

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.models import AppUser, Formation
from seed.load_demo_data import database_counts, ensure_non_production, load
from seed.validate_seed import UserSeed, load_seed_file


@pytest.fixture
def db_session():
    session = SessionLocal()
    transaction = session.begin()
    try:
        for table in (
            "institution", "formation", "specialty", "program", "subject",
            "program_subject", "tuition_fee", "role", "app_user",
        ):
            session.execute(text(f'SELECT 1 FROM "{table}" LIMIT 0'))
    except SQLAlchemyError as exc:
        if transaction.is_active:
            transaction.rollback()
        session.close()
        pytest.skip(f"local SA-17 database is unavailable or schema is not installed: {exc}")
    try:
        yield session
    finally:
        if transaction.is_active:
            transaction.rollback()
        session.close()


def test_load_is_idempotent_and_preserves_provenance_and_password(db_session) -> None:
    seed = load_seed_file("seed/demo_catalog.json")
    # A unique test-only account lets this verify hashing even if the regular
    # demo seed was loaded earlier. The whole test transaction is rolled back.
    test_password = token_urlsafe(32)
    seed.app_users.append(
        UserSeed(
            email="seed-loader-test@example.com",
            full_name="Seed Loader Test Account",
            role_code="interview_officer",
            institution_code="iit",
            is_active=False,
        )
    )

    before = database_counts(db_session)
    load(db_session, seed, test_password)
    after_first = database_counts(db_session)
    user_after_first = db_session.scalar(
        select(AppUser).where(AppUser.email == "seed-loader-test@example.com")
    )
    assert user_after_first is not None
    first_password_hash = user_after_first.password_hash
    load(db_session, seed, test_password)
    after_second = database_counts(db_session)

    assert after_first == after_second
    for table in ("formation", "specialty", "program", "subject", "program_subject", "tuition_fee", "role"):
        assert after_first[table]["total"] >= before[table]["total"]

    source_formation = db_session.scalar(select(Formation).where(Formation.code == "architecture"))
    demo_formation = db_session.scalar(select(Formation).where(Formation.code == "prepa-demo"))
    assert source_formation is not None and source_formation.is_demo is False
    assert "needs_review=true" in source_formation.source_note
    assert demo_formation is not None and demo_formation.is_demo is True
    assert "FICTITIOUS DEMO DATA" in demo_formation.source_note

    user = db_session.scalar(select(AppUser).where(AppUser.email == "seed-loader-test@example.com"))
    assert user is not None and user.is_active is False
    assert user.password_hash == first_password_hash
    assert user.password_hash != test_password
    PasswordHasher().verify(user.password_hash, test_password)


def test_refuses_production_environment() -> None:
    with pytest.raises(ValueError, match="APP_ENV is production"):
        ensure_non_production("production")


def test_allows_development_environment() -> None:
    ensure_non_production("development")
