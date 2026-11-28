import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VisitorSession(Base):
    __tablename__ = "visitor_session"
    __table_args__ = (
        CheckConstraint("turn_count >= 0", name="turn_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    turn_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VisitorMessage(Base):
    __tablename__ = "visitor_message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role_allowed"),
        Index("ix_visitor_message_session_created", "session_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visitor_session.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
