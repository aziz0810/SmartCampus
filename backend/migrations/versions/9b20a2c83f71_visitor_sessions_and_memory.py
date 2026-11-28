"""Add anonymous visitor sessions and temporary message memory.

Revision ID: 9b20a2c83f71
Revises: 95008f21dc74
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9b20a2c83f71"
down_revision: Union[str, Sequence[str], None] = "95008f21dc74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visitor_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "turn_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "turn_count >= 0",
            name=op.f("ck_visitor_session_turn_count_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visitor_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_visitor_session_token_hash")),
    )
    op.create_index(
        op.f("ix_visitor_session_expires_at"),
        "visitor_session",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "visitor_message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_visitor_message_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["visitor_session.id"],
            name=op.f("fk_visitor_message_session_id_visitor_session"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visitor_message")),
    )
    op.create_index(
        "ix_visitor_message_session_created",
        "visitor_message",
        ["session_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_visitor_message_session_created",
        table_name="visitor_message",
    )
    op.drop_table("visitor_message")
    op.drop_index(
        op.f("ix_visitor_session_expires_at"),
        table_name="visitor_session",
    )
    op.drop_table("visitor_session")
