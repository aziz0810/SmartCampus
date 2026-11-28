"""SA-12 integration tests: admission conditions and prerequisites on PostgreSQL.

Runs against the docker PostgreSQL configured in the root ``.env`` (or the
environment, inside the backend container). Skipped when it is unreachable.

Safety: inserted rows are demo rows (``is_demo=true``) inside a transaction
that is always rolled back. The downgrade/upgrade round trip only runs when
the database is empty, so it never deletes loaded data.
"""

from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pg_helpers import downgrade_round_trip

SA12_TABLES = (
    "qualification",
    "admission_condition",
    "admission_condition_qualification",
    "formation_prerequisite",
    "subject_prerequisite",
)
PREVIOUS_REVISION = "9b20a2c83f71"
SOURCE_NOTE = "SA-12 test (fictional demo row)"


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
    downgrade_round_trip(engine, PREVIOUS_REVISION, SA12_TABLES)
