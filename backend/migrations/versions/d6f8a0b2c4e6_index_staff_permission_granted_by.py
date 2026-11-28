"""Add the missing index for a nullable SA-13 staff-permission FK.

Revision ID: d6f8a0b2c4e6
Revises: c5e7a9b1d3f4
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d6f8a0b2c4e6"
down_revision: Union[str, Sequence[str], None] = "c5e7a9b1d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_staff_permission_granted_by_id"),
        "staff_permission",
        ["granted_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_staff_permission_granted_by_id"),
        table_name="staff_permission",
    )
