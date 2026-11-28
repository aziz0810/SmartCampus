import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AppUser,
    Formation,
    Institution,
    Program,
    ProgramSubject,
    Role,
    Specialty,
    Subject,
    TuitionFee,
)


def _insert(connection, model, **values):
    statement = insert(model).values(**values)
    if "id" not in model.__table__.c:
        connection.execute(statement)
        return None
    return connection.execute(statement.returning(model.id)).scalar_one()


def _expect_integrity_error(connection, statement):
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(statement)


def _catalog_fixture(connection):
    institution_id = _insert(connection, Institution, code="IIT", name="Demo IIT")
    formation_id = _insert(
        connection,
        Formation,
        institution_id=institution_id,
        code="LIC-INFO",
        name="Demo licence",
        kind="licence",
    )
    specialty_id = _insert(
        connection,
        Specialty,
        formation_id=formation_id,
        code="INFO",
        name="Demo informatique",
    )
    program_id = _insert(
        connection,
        Program,
        specialty_id=specialty_id,
        academic_year="2026-2027",
        duration_semesters=6,
    )
    subject_id = _insert(connection, Subject, code="MATH", name="Demo mathematics")
    role_id = _insert(connection, Role, code="admin", name="Demo administrator")
    return institution_id, formation_id, specialty_id, program_id, subject_id, role_id


def test_foreign_keys_reject_missing_references(migrated_schema):
    connection, _ = migrated_schema
    institution_id, formation_id, specialty_id, program_id, subject_id, role_id = _catalog_fixture(connection)

    invalid_rows = (
        insert(Formation).values(
            institution_id=99999999, code="BAD-FORM", name="Invalid", kind="licence"
        ),
        insert(Specialty).values(
            formation_id=99999999, code="BAD-SPEC", name="Invalid"
        ),
        insert(Program).values(
            specialty_id=99999999, academic_year="2027-2028", duration_semesters=1
        ),
        insert(ProgramSubject).values(
            program_id=99999999, subject_id=subject_id, semester=1, credits=1
        ),
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=99999999, semester=1, credits=1
        ),
        insert(TuitionFee).values(
            formation_id=99999999,
            academic_year="2026-2027",
            fee_type="registration",
            amount=10,
        ),
        insert(AppUser).values(
            email="invalid-role@example.com",
            full_name="Test User",
            password_hash="not-a-real-password",
            role_id=99999999,
        ),
        insert(AppUser).values(
            email="invalid-institution@example.com",
            full_name="Test User",
            password_hash="not-a-real-password",
            role_id=role_id,
            institution_id=99999999,
        ),
    )
    for statement in invalid_rows:
        _expect_integrity_error(connection, statement)


def test_natural_unique_keys_reject_duplicates(migrated_schema):
    connection, _ = migrated_schema
    institution_id, formation_id, specialty_id, program_id, subject_id, role_id = _catalog_fixture(connection)
    second_program_id = _insert(
        connection,
        Program,
        specialty_id=specialty_id,
        academic_year="2027-2028",
        duration_semesters=6,
    )

    duplicates = (
        insert(Institution).values(code="IIT", name="Duplicate"),
        insert(Formation).values(
            institution_id=institution_id, code="LIC-INFO", name="Duplicate", kind="licence"
        ),
        insert(Specialty).values(
            formation_id=formation_id, code="INFO", name="Duplicate"
        ),
        insert(Program).values(
            specialty_id=specialty_id,
            academic_year="2026-2027",
            duration_semesters=6,
        ),
        insert(Subject).values(code="MATH", name="Duplicate"),
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=subject_id, semester=1, credits=3
        ),
        insert(TuitionFee).values(
            formation_id=formation_id,
            academic_year="2026-2027",
            fee_type="registration",
            amount=10,
        ),
        insert(Role).values(code="admin", name="Duplicate"),
        insert(AppUser).values(
            email="staff@example.com",
            full_name="Test User",
            password_hash="not-a-real-password",
            role_id=role_id,
        ),
    )
    _insert(
        connection,
        TuitionFee,
        formation_id=formation_id,
        academic_year="2026-2027",
        fee_type="registration",
        amount=10,
    )
    _insert(
        connection,
        ProgramSubject,
        program_id=program_id,
        subject_id=subject_id,
        semester=1,
        credits=3,
    )
    _insert(
        connection,
        AppUser,
        email="staff@example.com",
        full_name="Test User",
        password_hash="not-a-real-password",
        role_id=role_id,
    )
    assert second_program_id != program_id
    for statement in duplicates:
        _expect_integrity_error(connection, statement)


def test_check_constraints_reject_invalid_ranges(migrated_schema):
    connection, _ = migrated_schema
    institution_id, formation_id, specialty_id, program_id, subject_id, _ = _catalog_fixture(connection)

    _expect_integrity_error(
        connection,
        insert(Program).values(
            specialty_id=specialty_id,
            academic_year="2028-2029",
            duration_semesters=0,
        ),
    )
    _expect_integrity_error(
        connection,
        insert(Program).values(
            specialty_id=specialty_id,
            academic_year="2029-2030",
            duration_semesters=None,
        ),
    )
    _expect_integrity_error(
        connection,
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=subject_id, semester=0, credits=3
        ),
    )
    _expect_integrity_error(
        connection,
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=subject_id, semester=1, credits=-1
        ),
    )
    _expect_integrity_error(
        connection,
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=subject_id, semester=None, credits=1
        ),
    )
    _expect_integrity_error(
        connection,
        insert(ProgramSubject).values(
            program_id=program_id, subject_id=subject_id, semester=1, credits=None
        ),
    )
    _expect_integrity_error(
        connection,
        insert(TuitionFee).values(
            formation_id=formation_id,
            academic_year="2026-2027",
            fee_type="invalid-amount-test",
            amount=-1,
        ),
    )
    _expect_integrity_error(
        connection,
        insert(TuitionFee).values(
            formation_id=formation_id,
            academic_year="2026-2027",
            fee_type="null-amount-test",
            amount=None,
        ),
    )
    _expect_integrity_error(
        connection,
        insert(Formation).values(
            institution_id=institution_id,
            code="BLANK-KIND",
            name="Invalid kind",
            kind="   ",
        ),
    )
    _expect_integrity_error(
        connection,
        insert(TuitionFee).values(
            formation_id=formation_id,
            academic_year="2026-2027",
            fee_type="   ",
            amount=1,
        ),
    )


def test_restrict_delete_fails_and_join_rows_cascade(migrated_schema):
    connection, _ = migrated_schema
    institution_id, formation_id, specialty_id, program_id, subject_id, role_id = _catalog_fixture(connection)
    link_program_id = _insert(
        connection,
        Program,
        specialty_id=specialty_id,
        academic_year="2027-2028",
        duration_semesters=6,
    )
    link_subject_id = _insert(connection, Subject, code="PHYS", name="Demo physics")
    _insert(
        connection,
        ProgramSubject,
        program_id=program_id,
        subject_id=subject_id,
        semester=1,
        credits=3,
    )
    _insert(
        connection,
        ProgramSubject,
        program_id=link_program_id,
        subject_id=link_subject_id,
        semester=1,
        credits=3,
    )
    _insert(
        connection,
        TuitionFee,
        formation_id=formation_id,
        academic_year="2026-2027",
        fee_type="registration",
        amount=10,
    )
    _insert(
        connection,
        AppUser,
        email="officer@example.com",
        full_name="Test Officer",
        password_hash="not-a-real-password",
        role_id=role_id,
        institution_id=institution_id,
    )

    _expect_integrity_error(
        connection,
        delete(Institution).where(Institution.id == institution_id),
    )
    _expect_integrity_error(
        connection,
        delete(Formation).where(Formation.id == formation_id),
    )
    _expect_integrity_error(
        connection,
        delete(Specialty).where(Specialty.id == specialty_id),
    )
    _expect_integrity_error(
        connection,
        delete(Role).where(Role.id == role_id),
    )

    connection.execute(delete(Subject).where(Subject.id == subject_id))
    assert connection.execute(
        select(ProgramSubject.subject_id).where(ProgramSubject.subject_id == subject_id)
    ).first() is None
    connection.execute(delete(Program).where(Program.id == link_program_id))
    assert connection.execute(
        select(ProgramSubject.program_id).where(ProgramSubject.program_id == link_program_id)
    ).first() is None
    assert connection.execute(
        select(ProgramSubject.subject_id).where(ProgramSubject.subject_id == link_subject_id)
    ).first() is None
