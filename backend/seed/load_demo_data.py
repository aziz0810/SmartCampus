"""Idempotently load the curated demo catalog into the configured database."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
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
from seed.validate_seed import CatalogSeed, load_seed_file


PASSWORD_HASHER = PasswordHasher()


def upsert(
    session: Session,
    model: type[Any],
    natural_key: dict[str, Any],
    values: dict[str, Any],
) -> tuple[Any, bool]:
    """Insert or update one row by its declared natural key; return (row, created)."""
    row = session.scalar(select(model).filter_by(**natural_key))
    created = row is None
    if created:
        row = model(**natural_key, **values)
        session.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    session.flush()
    return row, created


def _upsert_provenance_row(
    session: Session,
    model: type[Any],
    natural_key: dict[str, Any],
    values: dict[str, Any],
) -> tuple[Any, bool]:
    existing = session.scalar(select(model).filter_by(**natural_key))
    if existing is not None and bool(existing.is_demo) != bool(values["is_demo"]):
        raise ValueError(
            f"refusing to overwrite {model.__tablename__} row {natural_key}: "
            "seed and database disagree about is_demo provenance"
        )
    return upsert(session, model, natural_key, values)


def load(session: Session, data: CatalogSeed, demo_password: str) -> dict[str, int]:
    """Load all seed sections in dependency order inside the caller's transaction."""
    if len(demo_password) < 16:
        raise ValueError("DEMO_USER_PASSWORD must contain at least 16 characters")

    created = 0
    updated = 0

    def record(result: tuple[Any, bool]) -> Any:
        nonlocal created, updated
        row, was_created = result
        if was_created:
            created += 1
        else:
            updated += 1
        return row

    role_by_code: dict[str, Role] = {}
    for item in data.roles:
        role_by_code[item.code.casefold()] = record(
            upsert(session, Role, {"code": item.code}, {"name": item.name})
        )

    institution_by_code: dict[str, Institution] = {}
    for item in data.institutions:
        institution_by_code[item.code.casefold()] = record(
            upsert(
                session,
                Institution,
                {"code": item.code},
                {"name": item.name, "website_url": item.website_url},
            )
        )

    formation_by_code: dict[str, Formation] = {}
    for item in data.formations:
        institution = institution_by_code[item.institution_code.casefold()]
        formation_by_code[item.code.casefold()] = record(
            _upsert_provenance_row(
                session,
                Formation,
                {"institution_id": institution.id, "code": item.code},
                {
                    "name": item.name,
                    "kind": item.kind,
                    "description": item.description,
                    "is_demo": item.is_demo,
                    "source_note": item.source_note,
                },
            )
        )

    specialty_by_key: dict[tuple[str, str], Specialty] = {}
    for item in data.specialties:
        formation = formation_by_code[item.formation_code.casefold()]
        specialty_by_key[(item.formation_code.casefold(), item.code.casefold())] = record(
            _upsert_provenance_row(
                session,
                Specialty,
                {"formation_id": formation.id, "code": item.code},
                {
                    "name": item.name,
                    "description": item.description,
                    "is_demo": item.is_demo,
                    "source_note": item.source_note,
                },
            )
        )

    program_by_code: dict[str, Program] = {}
    for item in data.programs:
        specialty = specialty_by_key[(item.formation_code.casefold(), item.specialty_code.casefold())]
        program_by_code[item.code.casefold()] = record(
            _upsert_provenance_row(
                session,
                Program,
                {"specialty_id": specialty.id, "academic_year": item.academic_year},
                {
                    "duration_semesters": item.duration_semesters,
                    "description": item.description,
                    "is_demo": item.is_demo,
                    "source_note": item.source_note,
                },
            )
        )

    subject_by_code: dict[str, Subject] = {}
    for item in data.subjects:
        subject_by_code[item.code.casefold()] = record(
            _upsert_provenance_row(
                session,
                Subject,
                {"code": item.code},
                {
                    "name": item.name,
                    "description": item.description,
                    "is_demo": item.is_demo,
                    "source_note": item.source_note,
                },
            )
        )

    for item in data.program_subjects:
        program = program_by_code[item.program_code.casefold()]
        subject = subject_by_code[item.subject_code.casefold()]
        record(
            upsert(
                session,
                ProgramSubject,
                {"program_id": program.id, "subject_id": subject.id},
                {"semester": item.semester, "credits": item.credits, "is_optional": item.is_optional},
            )
        )

    for item in data.tuition_fees:
        formation = formation_by_code[item.formation_code.casefold()]
        record(
            _upsert_provenance_row(
                session,
                TuitionFee,
                {
                    "formation_id": formation.id,
                    "academic_year": item.academic_year,
                    "fee_type": item.fee_type,
                },
                {
                    "amount": item.amount,
                    "currency": item.currency,
                    "is_demo": item.is_demo,
                    "source_note": item.source_note,
                },
            )
        )

    for item in data.app_users:
        role = role_by_code[item.role_code.casefold()]
        institution = (
            institution_by_code[item.institution_code.casefold()]
            if item.institution_code
            else None
        )
        key = {"email": item.email}
        user = session.scalar(select(AppUser).filter_by(**key))
        values = {
            "full_name": item.full_name,
            "is_active": item.is_active,
            "role_id": role.id,
            "institution_id": institution.id if institution else None,
        }
        if user is None:
            values["password_hash"] = PASSWORD_HASHER.hash(demo_password)
            user = AppUser(**key, **values)
            session.add(user)
            session.flush()
            created += 1
        else:
            for field, value in values.items():
                setattr(user, field, value)
            # Existing passwords are never overwritten by a seed rerun.
            session.flush()
            updated += 1

    return {"created": created, "updated": updated}


def database_counts(session: Session) -> dict[str, dict[str, int]]:
    """Return totals and provenance counts where the current schema stores them."""
    counts: dict[str, dict[str, int]] = {}
    provenance_models = {
        "formation": Formation,
        "specialty": Specialty,
        "program": Program,
        "subject": Subject,
        "tuition_fee": TuitionFee,
    }
    for name, model in provenance_models.items():
        total, demo = session.execute(
            select(func.count(model.id), func.count(model.id).filter(model.is_demo.is_(True)))
        ).one()
        counts[name] = {"total": total, "demo": demo, "source_backed": total - demo}

    for name, model in (("institution", Institution), ("role", Role)):
        counts[name] = {"total": session.scalar(select(func.count(model.id))) or 0}

    user_total, demo_users = session.execute(
        select(
            func.count(AppUser.id),
            func.count(AppUser.id).filter(AppUser.email.ilike("%@example.com")),
        )
    ).one()
    counts["app_user"] = {
        "total": user_total,
        "demo": demo_users,
        "other": user_total - demo_users,
    }

    mapping_total, mapping_demo = session.execute(
        select(
            func.count(ProgramSubject.program_id),
            func.count(ProgramSubject.program_id).filter(Program.is_demo.is_(True)),
        ).select_from(ProgramSubject).join(Program, Program.id == ProgramSubject.program_id)
    ).one()
    counts["program_subject"] = {
        "total": mapping_total,
        "demo_programs": mapping_demo,
        "source_programs": mapping_total - mapping_demo,
    }
    return counts


def print_counts(counts: dict[str, dict[str, int]]) -> None:
    for table, values in counts.items():
        detail = ", ".join(f"{key}={value}" for key, value in values.items())
        print(f"{table}: {detail}")


def ensure_non_production(app_env: str) -> None:
    if app_env.casefold() in {"prod", "production"}:
        raise ValueError("Refusing to load demo seed data while APP_ENV is production")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the validated SmartCampus demo catalog.")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).with_name("demo_catalog.json"),
        help="seed JSON file (default: backend/seed/demo_catalog.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and roll back the transaction")
    args = parser.parse_args()

    seed = load_seed_file(args.file)
    try:
        ensure_non_production(settings.app_env)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    password = settings.demo_user_password.get_secret_value() if settings.demo_user_password else ""
    if not password:
        raise SystemExit("Set a non-empty DEMO_USER_PASSWORD in the ignored .env file before loading")

    session = SessionLocal()
    try:
        with session.begin():
            outcome = load(session, seed, password)
            counts = database_counts(session)
            if args.dry_run:
                # Raise an internal sentinel so the context manager rolls back.
                raise _DryRunComplete(outcome, counts)
    except _DryRunComplete as dry_run:
        print("Dry run complete; transaction rolled back.")
        print(f"Rows created/updated: {dry_run.outcome}")
        print_counts(dry_run.counts)
        return
    finally:
        session.close()

    print(f"Seed committed; rows created/updated: {outcome}")
    print_counts(counts)


class _DryRunComplete(Exception):
    def __init__(self, outcome: dict[str, int], counts: dict[str, dict[str, int]]) -> None:
        self.outcome = outcome
        self.counts = counts


if __name__ == "__main__":
    main()
