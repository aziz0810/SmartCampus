from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ProvenanceMixin, TimestampMixin


class Institution(TimestampMixin, Base):
    __tablename__ = "institution"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    website_url: Mapped[str | None] = mapped_column(String(500))


class Formation(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "formation"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_formation_institution_code"),
        CheckConstraint("length(btrim(kind)) > 0", name="kind_non_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)


class Specialty(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "specialty"
    __table_args__ = (
        UniqueConstraint("formation_id", "code", name="uq_specialty_formation_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


class Program(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "program"
    __table_args__ = (
        UniqueConstraint("specialty_id", "academic_year", name="uq_program_specialty_year"),
        CheckConstraint("duration_semesters > 0", name="duration_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialty.id", ondelete="RESTRICT")
    )
    academic_year: Mapped[str] = mapped_column(String(9))
    duration_semesters: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Subject(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


class ProgramSubject(Base):
    __tablename__ = "program_subject"
    __table_args__ = (
        CheckConstraint("semester > 0", name="semester_positive"),
        CheckConstraint("credits >= 0", name="credits_non_negative"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    semester: Mapped[int] = mapped_column(nullable=False)
    credits: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class TuitionFee(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "tuition_fee"
    __table_args__ = (
        UniqueConstraint(
            "formation_id",
            "academic_year",
            "fee_type",
            name="uq_tuition_fee_formation_year_type",
        ),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("length(btrim(fee_type)) > 0", name="fee_type_non_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT")
    )
    academic_year: Mapped[str] = mapped_column(String(9))
    fee_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), server_default="TND")


# --- SA-12: admission conditions and prerequisites -------------------------

QUALIFICATION_KINDS = ("bac", "prepa", "licence", "master", "ingenieur", "other")
ADMISSION_ROUTES = ("bac", "prepa", "licence", "master", "other")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Qualification(ProvenanceMixin, TimestampMixin, Base):
    """Reference list of diplomas (e.g. "Prépa MP", "Licence en génie logiciel").

    Shared by admission conditions and, later, candidate profiles and
    equivalence requests, so a diploma is stored once.
    """

    __tablename__ = "qualification"
    __table_args__ = (
        CheckConstraint(_in_list("kind", QUALIFICATION_KINDS), name="kind_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    field: Mapped[str | None] = mapped_column(String(255))


class AdmissionCondition(ProvenanceMixin, TimestampMixin, Base):
    """One way into a formation: entry year, route and the rule that applies.

    ``specialty_id`` is optional and, when set, must belong to ``formation_id``
    (checked by the service layer, not by the database).
    """

    __tablename__ = "admission_condition"
    __table_args__ = (
        CheckConstraint("entry_year > 0", name="entry_year_positive"),
        CheckConstraint(_in_list("route", ADMISSION_ROUTES), name="route_allowed"),
        CheckConstraint("min_average >= 0 AND min_average <= 20", name="min_average_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT"), index=True
    )
    specialty_id: Mapped[int | None] = mapped_column(
        ForeignKey("specialty.id", ondelete="RESTRICT"), index=True
    )
    entry_year: Mapped[int] = mapped_column(SmallInteger)
    route: Mapped[str] = mapped_column(String(20))
    min_average: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    selection_method: Mapped[str | None] = mapped_column(Text)
    academic_year: Mapped[str | None] = mapped_column(String(9))
    description: Mapped[str] = mapped_column(Text)


class AdmissionConditionQualification(Base):
    """Diplomas accepted by an admission condition."""

    __tablename__ = "admission_condition_qualification"

    # Explicit FK names: the naming convention would exceed PostgreSQL's
    # 63-character identifier limit for this table.
    admission_condition_id: Mapped[int] = mapped_column(
        ForeignKey(
            "admission_condition.id",
            ondelete="CASCADE",
            name="fk_admission_condition_qualification_condition",
        ),
        primary_key=True,
    )
    qualification_id: Mapped[int] = mapped_column(
        ForeignKey(
            "qualification.id",
            ondelete="RESTRICT",
            name="fk_admission_condition_qualification_qualification",
        ),
        primary_key=True,
        index=True,
    )


class FormationPrerequisite(ProvenanceMixin, TimestampMixin, Base):
    """Knowledge expected before starting a formation (or one of its specialties)."""

    __tablename__ = "formation_prerequisite"

    id: Mapped[int] = mapped_column(primary_key=True)
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT"), index=True
    )
    specialty_id: Mapped[int | None] = mapped_column(
        ForeignKey("specialty.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str] = mapped_column(Text)


class SubjectPrerequisite(Base):
    """A subject that must be followed before another one."""

    __tablename__ = "subject_prerequisite"
    __table_args__ = (
        CheckConstraint("subject_id <> required_subject_id", name="not_self"),
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )
    required_subject_id: Mapped[int] = mapped_column(
        ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True, index=True
    )
