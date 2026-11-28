"""SA-13: candidates, responsables, conversations and applications.

Visitors without an account stay in ``visitor_session`` / ``visitor_message``
(SA-25/26); accounts and roles stay in ``app_user`` / ``role`` (SA-28).
This module adds what an identified candidate and a responsable need:

- candidate_profile, staff_permission
- conversation, conversation_message (permanent, unlike visitor sessions)
- preregistration, equivalence_request, request_status_history
- appointment_slot, appointment, interview

Status values are the ones of the business process document
("SmartCampus AI — 1. Acteurs et processus métier"), in French uppercase.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ProvenanceMixin, TimestampMixin

STAFF_PERMISSIONS = ("academique", "entretien", "direction", "administration")
CONVERSATION_CHANNELS = ("texte", "audio")
MESSAGE_ROLES = ("user", "assistant")

PREREGISTRATION_STATUSES = (
    "BROUILLON", "SOUMISE", "QCM_EN_ATTENTE", "QCM_TERMINE", "ENTRETIEN",
    "ADMISE", "REFUSEE", "INSCRITE", "ABANDONNEE",
)
PREREGISTRATION_CLOSED = ("REFUSEE", "ABANDONNEE")
EQUIVALENCE_STATUSES = (
    "BROUILLON", "SOUMISE", "EN_VERIFICATION", "INCOMPLETE", "EN_EVALUATION",
    "ACCEPTEE", "PARTIELLE", "REFUSEE",
)
EQUIVALENCE_DECIDED = ("ACCEPTEE", "PARTIELLE", "REFUSEE")
APPOINTMENT_MODES = ("presentiel", "visio")
APPOINTMENT_STATUSES = ("PROPOSE", "CONFIRME", "REALISE", "ANNULE", "ABSENT")
APPOINTMENT_ACTIVE = ("PROPOSE", "CONFIRME")
INTERVIEW_STATUSES = ("A_PREPARER", "PRET", "REALISE")
INTERVIEW_RESULTS = ("FAVORABLE", "COMPLEMENT_REQUIS", "DEFAVORABLE")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


# --- People ----------------------------------------------------------------


class CandidateProfile(ProvenanceMixin, TimestampMixin, Base):
    """Academic profile of a candidate (same fields as the LLM profile extraction)."""

    __tablename__ = "candidate_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), unique=True
    )
    academic_level: Mapped[str | None] = mapped_column(String(255))
    qualification_id: Mapped[int | None] = mapped_column(
        ForeignKey("qualification.id", ondelete="RESTRICT"), index=True
    )
    favorite_subjects: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    career_goal: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    preferred_language: Mapped[str | None] = mapped_column(String(20))


class StaffPermission(TimestampMixin, Base):
    """What a responsable may do, and for which institution (IIT/ISB)."""

    __tablename__ = "staff_permission"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission", "institution_id",
            name="uq_staff_permission_user_permission_institution",
        ),
        CheckConstraint(_in_list("permission", STAFF_PERMISSIONS), name="permission_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    permission: Mapped[str] = mapped_column(String(20))
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT"), index=True
    )
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )


# --- Conversations ---------------------------------------------------------


class Conversation(TimestampMixin, Base):
    """A candidate's permanent conversation.

    ``visitor_session_id`` keeps the link to the guest session it came from;
    it becomes NULL when that session expires and is purged.
    """

    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint(_in_list("channel", CONVERSATION_CHANNELS), name="channel_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    visitor_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("visitor_session.id", ondelete="SET NULL"), unique=True
    )
    channel: Mapped[str] = mapped_column(String(10), server_default="texte")
    language: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(255))


class ConversationMessage(Base):
    __tablename__ = "conversation_message"
    __table_args__ = (
        CheckConstraint(_in_list("role", MESSAGE_ROLES), name="role_allowed"),
        Index(
            "ix_conversation_message_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(20))
    intent: Mapped[str | None] = mapped_column(String(30))
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# --- Requests --------------------------------------------------------------


class Preregistration(ProvenanceMixin, TimestampMixin, Base):
    """BROUILLON → SOUMISE → QCM_EN_ATTENTE → QCM_TERMINE → ENTRETIEN →
    ADMISE / REFUSEE; ADMISE → INSCRITE; ABANDONNEE from any open state."""

    __tablename__ = "preregistration"
    __table_args__ = (
        CheckConstraint(_in_list("status", PREREGISTRATION_STATUSES), name="status_allowed"),
        CheckConstraint(
            "status IN ('BROUILLON', 'ABANDONNEE') "
            "OR (consent_at IS NOT NULL AND submitted_at IS NOT NULL)",
            name="submitted_with_consent",
        ),
        CheckConstraint(
            "status NOT IN ('ADMISE', 'REFUSEE', 'INSCRITE') OR decided_at IS NOT NULL",
            name="decision_has_date",
        ),
        CheckConstraint(
            "status <> 'REFUSEE' OR decision_reason IS NOT NULL", name="refusal_has_reason"
        ),
        Index(
            "uq_preregistration_one_active",
            "candidate_id",
            "formation_id",
            unique=True,
            postgresql_where=text("status NOT IN ('REFUSEE', 'ABANDONNEE')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT"), index=True
    )
    specialty_id: Mapped[int | None] = mapped_column(
        ForeignKey("specialty.id", ondelete="RESTRICT"), index=True
    )
    academic_year: Mapped[str | None] = mapped_column(String(9))
    status: Mapped[str] = mapped_column(String(20), server_default="BROUILLON")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class EquivalenceRequest(ProvenanceMixin, TimestampMixin, Base):
    """BROUILLON → SOUMISE → EN_VERIFICATION (⇄ INCOMPLETE) → EN_EVALUATION →
    ACCEPTEE / PARTIELLE / REFUSEE, decided by a responsable with a reason."""

    __tablename__ = "equivalence_request"
    __table_args__ = (
        CheckConstraint(_in_list("status", EQUIVALENCE_STATUSES), name="status_allowed"),
        CheckConstraint(
            "status = 'BROUILLON' OR (consent_at IS NOT NULL AND submitted_at IS NOT NULL)",
            name="submitted_with_consent",
        ),
        CheckConstraint(
            "status NOT IN ('ACCEPTEE', 'PARTIELLE', 'REFUSEE') "
            "OR (decided_at IS NOT NULL AND decided_by_id IS NOT NULL "
            "AND decision_reason IS NOT NULL)",
            name="decision_complete",
        ),
        CheckConstraint("target_entry_year > 0", name="target_entry_year_positive"),
        Index(
            "uq_equivalence_request_one_active",
            "candidate_id",
            "target_formation_id",
            unique=True,
            postgresql_where=text("status NOT IN ('ACCEPTEE', 'PARTIELLE', 'REFUSEE')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    target_formation_id: Mapped[int] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT"), index=True
    )
    target_entry_year: Mapped[int | None] = mapped_column(SmallInteger)
    qualification_id: Mapped[int | None] = mapped_column(
        ForeignKey("qualification.id", ondelete="RESTRICT"), index=True
    )
    previous_institution: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), server_default="BROUILLON")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)


# --- Appointments and interviews -------------------------------------------


class AppointmentSlot(TimestampMixin, Base):
    """A time slot offered by a responsable."""

    __tablename__ = "appointment_slot"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint(_in_list("mode", APPOINTMENT_MODES), name="mode_allowed"),
        UniqueConstraint("staff_user_id", "starts_at", name="uq_appointment_slot_staff_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT"), index=True
    )
    staff_user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(20), server_default="presentiel")
    is_open: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Appointment(TimestampMixin, Base):
    """PROPOSE → CONFIRME → REALISE, or ANNULE / ABSENT. A rescheduled
    appointment is a new row pointing to the previous one."""

    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint(_in_list("status", APPOINTMENT_STATUSES), name="status_allowed"),
        CheckConstraint(
            "status NOT IN ('CONFIRME', 'REALISE') OR confirmed_at IS NOT NULL",
            name="confirmed_has_date",
        ),
        CheckConstraint("status <> 'ANNULE' OR cancelled_at IS NOT NULL", name="cancelled_has_date"),
        CheckConstraint("previous_appointment_id <> id", name="not_own_previous"),
        Index(
            "uq_appointment_one_active_per_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('PROPOSE', 'CONFIRME')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    preregistration_id: Mapped[int | None] = mapped_column(
        ForeignKey("preregistration.id", ondelete="RESTRICT"), index=True
    )
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("appointment_slot.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), server_default="PROPOSE")
    previous_appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="RESTRICT"), unique=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class Interview(TimestampMixin, Base):
    """A_PREPARER → PRET → REALISE, with a result once REALISE.
    FAVORABLE leads the pre-registration to ADMISE, DEFAVORABLE to REFUSEE."""

    __tablename__ = "interview"
    __table_args__ = (
        CheckConstraint(_in_list("status", INTERVIEW_STATUSES), name="status_allowed"),
        CheckConstraint(
            f"result IS NULL OR {_in_list('result', INTERVIEW_RESULTS)}", name="result_allowed"
        ),
        CheckConstraint("result IS NULL OR status = 'REALISE'", name="result_only_when_done"),
        CheckConstraint(
            "status <> 'REALISE' OR (completed_at IS NOT NULL AND observations IS NOT NULL)",
            name="done_has_observations",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preregistration_id: Mapped[int] = mapped_column(
        ForeignKey("preregistration.id", ondelete="RESTRICT"), unique=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="RESTRICT"), index=True
    )
    interviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), server_default="A_PREPARER")
    preparation_summary: Mapped[str | None] = mapped_column(Text)
    observations: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(String(20))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- History ---------------------------------------------------------------


class RequestStatusHistory(Base):
    """Every status change of a request, appointment or interview:
    from → to, who (NULL = system), when and why. Exactly one target is set."""

    __tablename__ = "request_status_history"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(preregistration_id, equivalence_request_id, appointment_id, "
            "interview_id) = 1",
            name="exactly_one_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preregistration_id: Mapped[int | None] = mapped_column(
        ForeignKey("preregistration.id", ondelete="RESTRICT"), index=True
    )
    # Explicit name: the convention would exceed PostgreSQL's 63-character limit.
    equivalence_request_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "equivalence_request.id",
            ondelete="RESTRICT",
            name="fk_request_status_history_equivalence_request",
        ),
        index=True,
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="RESTRICT"), index=True
    )
    interview_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
