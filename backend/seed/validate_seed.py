"""Validate the curated seed file before it reaches the database."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


ACADEMIC_YEAR = re.compile(r"^\d{4}-\d{4}$")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b")
INTERNATIONAL_PHONE = re.compile(r"(?<!\w)(?:\+|00)\d{1,3}(?:[\s().-]?\d){7,14}(?!\w)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)
SENSITIVE_KEYS = {"password", "password_hash", "secret", "token", "api_key", "authorization"}


class SeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InstitutionSeed(SeedModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    website_url: str | None = Field(default=None, max_length=500)


class RoleSeed(SeedModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)


class UserSeed(SeedModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    role_code: str = Field(min_length=1, max_length=30)
    institution_code: str | None = Field(default=None, max_length=20)
    is_active: bool

    @model_validator(mode="after")
    def email_is_demo_address(self) -> "UserSeed":
        if not self.email.lower().endswith("@example.com"):
            raise ValueError("demo app_user email must use the reserved example.com domain")
        return self


class FormationSeed(SeedModel):
    code: str = Field(min_length=1, max_length=50)
    institution_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=50)
    description: str | None = None
    is_demo: bool
    source_note: str | None = None


class SpecialtySeed(SeedModel):
    code: str = Field(min_length=1, max_length=50)
    formation_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_demo: bool
    source_note: str | None = None


class ProgramSeed(SeedModel):
    code: str = Field(min_length=1, max_length=100)
    formation_code: str = Field(min_length=1, max_length=50)
    specialty_code: str = Field(min_length=1, max_length=50)
    academic_year: str = Field(pattern=ACADEMIC_YEAR.pattern, max_length=9)
    duration_semesters: int = Field(gt=0)
    description: str | None = None
    is_demo: bool
    source_note: str | None = None


class SubjectSeed(SeedModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_demo: bool
    source_note: str | None = None


class ProgramSubjectSeed(SeedModel):
    program_code: str = Field(min_length=1, max_length=100)
    subject_code: str = Field(min_length=1, max_length=50)
    semester: int = Field(gt=0)
    credits: Decimal = Field(ge=0, max_digits=4, decimal_places=1)
    is_optional: bool = False


class TuitionFeeSeed(SeedModel):
    formation_code: str = Field(min_length=1, max_length=50)
    academic_year: str = Field(pattern=ACADEMIC_YEAR.pattern, max_length=9)
    fee_type: str = Field(min_length=1, max_length=30)
    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="TND", min_length=3, max_length=3)
    is_demo: bool
    source_note: str | None = None


class CatalogSeed(SeedModel):
    meta: dict[str, str] = Field(default_factory=dict)
    institutions: list[InstitutionSeed]
    roles: list[RoleSeed]
    app_users: list[UserSeed]
    formations: list[FormationSeed]
    specialties: list[SpecialtySeed]
    programs: list[ProgramSeed]
    subjects: list[SubjectSeed]
    program_subjects: list[ProgramSubjectSeed]
    tuition_fees: list[TuitionFeeSeed]

    @model_validator(mode="after")
    def validate_references_and_unique_keys(self) -> "CatalogSeed":
        def unique(items: list[Any], key_fn: Any, label: str) -> set[Any]:
            seen: set[Any] = set()
            for index, item in enumerate(items):
                key = key_fn(item)
                if key in seen:
                    raise ValueError(f"duplicate {label} at entry {index}: {key}")
                seen.add(key)
            return seen

        institutions = unique(self.institutions, lambda row: row.code.casefold(), "institution code")
        roles = unique(self.roles, lambda row: row.code.casefold(), "role code")
        formations = unique(
            self.formations,
            lambda row: (row.institution_code.casefold(), row.code.casefold()),
            "formation (institution, code)",
        )
        specialties = unique(
            self.specialties,
            lambda row: (row.formation_code.casefold(), row.code.casefold()),
            "specialty (formation, code)",
        )
        programs = unique(
            self.programs,
            lambda row: (row.formation_code.casefold(), row.specialty_code.casefold(), row.academic_year),
            "program (formation, specialty, academic_year)",
        )
        unique(self.programs, lambda row: row.code.casefold(), "program code")
        subjects = unique(self.subjects, lambda row: row.code.casefold(), "subject code")
        unique(self.app_users, lambda row: row.email.casefold(), "app_user email")
        unique(
            self.program_subjects,
            lambda row: (row.program_code.casefold(), row.subject_code.casefold()),
            "program_subject key",
        )
        unique(
            self.tuition_fees,
            lambda row: (row.formation_code.casefold(), row.academic_year, row.fee_type.casefold()),
            "tuition_fee key",
        )

        institution_codes = {row.code.casefold() for row in self.institutions}
        role_codes = {row.code.casefold() for row in self.roles}
        formation_codes = {row.code.casefold() for row in self.formations}
        specialty_keys = {(row.formation_code.casefold(), row.code.casefold()) for row in self.specialties}
        program_by_code = {row.code.casefold(): row for row in self.programs}
        subject_codes = {row.code.casefold() for row in self.subjects}

        for index, row in enumerate(self.formations):
            if row.institution_code.casefold() not in institution_codes:
                raise ValueError(f"formations[{index}] references unknown institution {row.institution_code!r}")
        for index, row in enumerate(self.specialties):
            if row.formation_code.casefold() not in formation_codes:
                raise ValueError(f"specialties[{index}] references unknown formation {row.formation_code!r}")
        for index, row in enumerate(self.programs):
            if (row.formation_code.casefold(), row.specialty_code.casefold()) not in specialty_keys:
                raise ValueError(
                    f"programs[{index}] references unknown specialty "
                    f"{row.specialty_code!r} for formation {row.formation_code!r}"
                )
        for index, row in enumerate(self.program_subjects):
            program = program_by_code.get(row.program_code.casefold())
            if program is None:
                raise ValueError(f"program_subjects[{index}] references unknown program {row.program_code!r}")
            if row.subject_code.casefold() not in subject_codes:
                raise ValueError(f"program_subjects[{index}] references unknown subject {row.subject_code!r}")
            if row.semester > program.duration_semesters:
                raise ValueError(
                    f"program_subjects[{index}] semester {row.semester} exceeds "
                    f"program duration {program.duration_semesters}"
                )
        for index, row in enumerate(self.tuition_fees):
            if row.formation_code.casefold() not in formation_codes:
                raise ValueError(f"tuition_fees[{index}] references unknown formation {row.formation_code!r}")
        for index, row in enumerate(self.app_users):
            if row.role_code.casefold() not in role_codes:
                raise ValueError(f"app_users[{index}] references unknown role {row.role_code!r}")
            if row.institution_code and row.institution_code.casefold() not in institution_codes:
                raise ValueError(f"app_users[{index}] references unknown institution {row.institution_code!r}")
        return self


def _scan_sensitive_content(value: Any, path: str = "$", key: str | None = None) -> None:
    if key and key.casefold() in SENSITIVE_KEYS:
        raise ValueError(f"sensitive field is not allowed in seed data: {path}")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _scan_sensitive_content(child, f"{path}.{child_key}", str(child_key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_sensitive_content(child, f"{path}[{index}]")
    elif isinstance(value, str):
        for match in EMAIL.finditer(value):
            if match.group(1).casefold() != "example.com":
                raise ValueError(f"email outside example.com is not allowed in seed data: {path}")
        if IBAN.search(value):
            raise ValueError(f"bank account identifiers are not allowed in seed data: {path}")
        if INTERNATIONAL_PHONE.search(value):
            raise ValueError(f"phone numbers are not allowed in seed data: {path}")


def validate_seed(data: dict[str, Any]) -> CatalogSeed:
    _scan_sensitive_content(data)
    return CatalogSeed.model_validate(data)


def load_seed_file(path: str | Path) -> CatalogSeed:
    import json

    seed_path = Path(path)
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read seed JSON {seed_path}: {exc}") from exc
    try:
        return validate_seed(data)
    except ValidationError as exc:
        raise ValueError(f"seed validation failed for {seed_path}:\n{exc}") from exc


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate the SmartCampus catalog seed JSON.")
    parser.add_argument("file", nargs="?", default=Path(__file__).with_name("demo_catalog.json"))
    args = parser.parse_args()
    parsed = load_seed_file(args.file)
    print(f"Valid seed: {args.file} ({len(parsed.institutions)} institutions, "
          f"{len(parsed.formations)} formations, {len(parsed.programs)} programs)")
