"""auth: add claimed_by_user_id to visitor_session, seed roles

Revision ID: a1b2c3d4e5f6
Revises: 9b20a2c83f71
Create Date: 2026-11-28 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9b20a2c83f71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add claimed_by_user_id to visitor_session
    op.add_column(
        "visitor_session",
        sa.Column("claimed_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_visitor_session_claimed_by_user_id",
        "visitor_session",
        ["claimed_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_visitor_session_claimed_by_user_id_app_user",
        "visitor_session",
        "app_user",
        ["claimed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Seed the two built-in roles if they don't exist yet
    op.execute(
        """
        INSERT INTO role (code, name)
        VALUES
            ('candidat',    'Candidat'),
            ('responsable', 'Responsable')
        ON CONFLICT (code) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_visitor_session_claimed_by_user_id_app_user",
        "visitor_session",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_visitor_session_claimed_by_user_id", table_name="visitor_session"
    )
    op.drop_column("visitor_session", "claimed_by_user_id")
    # Do not remove roles to avoid breaking existing users.
