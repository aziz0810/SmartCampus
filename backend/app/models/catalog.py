from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
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
    duration_semesters: Mapped[int | None]
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
    semester: Mapped[int | None]
    credits: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT")
    )
    academic_year: Mapped[str] = mapped_column(String(9))
    fee_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="TND")
