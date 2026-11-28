"""SA-14: official documents, their versions, change history and sync jobs.

Only documents imported by a responsable are stored here; candidates' own
files belong to the application tables (SA-13). Passages and embeddings are
owned by SA-45/46 and reference ``document_version.id``.

A document is never erased: removing it means ``status = 'withdrawn'``, which
keeps its files and history.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ProvenanceMixin, TimestampMixin

DOCUMENT_CATEGORIES = ("admission", "programme", "reglement", "frais", "calendrier", "autre")
DOCUMENT_STATUSES = ("draft", "published", "withdrawn")
DOCUMENT_MIME_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
EXTRACTION_STATUSES = ("pending", "ok", "partial", "failed")
DOCUMENT_EVENT_TYPES = ("created", "updated", "version_added", "published", "withdrawn")
SYNC_ACTIONS = ("index", "reindex", "remove")
SYNC_STATUSES = ("pending", "running", "done", "failed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Document(ProvenanceMixin, TimestampMixin, Base):
    """An official document (admission rules, programme, fees...)."""

    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(_in_list("category", DOCUMENT_CATEGORIES), name="category_allowed"),
        CheckConstraint(_in_list("status", DOCUMENT_STATUSES), name="status_allowed"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_has_date"
        ),
        CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL", name="withdrawn_has_date"
        ),
        Index("ix_document_institution_status", "institution_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT")
    )
    formation_id: Mapped[int | None] = mapped_column(
        ForeignKey("formation.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(10), server_default="fr")
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(TimestampMixin, Base):
    """One uploaded file of a document. Exactly one version can be current."""

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_version_document_number"
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(_in_list("mime_type", DOCUMENT_MIME_TYPES), name="mime_type_allowed"),
        CheckConstraint(
            _in_list("extraction_status", EXTRACTION_STATUSES), name="extraction_status_allowed"
        ),
        CheckConstraint("char_length(checksum_sha256) = 64", name="checksum_length"),
        Index(
            "uq_document_version_one_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="RESTRICT"), index=True
    )
    version_number: Mapped[int] = mapped_column(SmallInteger)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    extraction_status: Mapped[str] = mapped_column(String(20), server_default="pending")
    extraction_note: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentEvent(Base):
    """Append-only history of what happened to a document (SA-48)."""

    __tablename__ = "document_event"
    __table_args__ = (
        CheckConstraint(_in_list("event_type", DOCUMENT_EVENT_TYPES), name="event_type_allowed"),
        Index("ix_document_event_document_occurred", "document_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="RESTRICT"))
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_version.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentSyncJob(TimestampMixin, Base):
    """Background update of the vector index after an event (SA-49/50).

    One job per event: a retry reuses the same row (``attempts`` + 1) instead
    of creating a new one, so retries cannot create duplicates.
    """

    __tablename__ = "document_sync_job"
    __table_args__ = (
        CheckConstraint(_in_list("action", SYNC_ACTIONS), name="action_allowed"),
        CheckConstraint(_in_list("status", SYNC_STATUSES), name="status_allowed"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint(
            "action = 'remove' OR version_id IS NOT NULL", name="indexing_has_version"
        ),
        CheckConstraint(
            "status <> 'done' OR finished_at IS NOT NULL", name="done_has_finish_date"
        ),
        Index("ix_document_sync_job_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("document_event.id", ondelete="RESTRICT"), unique=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="RESTRICT"), index=True
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_version.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    passages_count: Mapped[int | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
