"""Require values protected by positive/non-negative checks.

Revision ID: a17c3d8e4b61
Revises: d6f8a0b2c4e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a17c3d8e4b61"
down_revision: Union[str, Sequence[str], None] = "d6f8a0b2c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REQUIRED_VALUES = (
    ("program", "duration_semesters", sa.Integer()),
    ("program_subject", "semester", sa.Integer()),
    ("program_subject", "credits", sa.Numeric(precision=4, scale=1)),
    ("tuition_fee", "amount", sa.Numeric(precision=10, scale=2)),
)
_NONEMPTY_CATEGORIES = (("formation", "kind"), ("tuition_fee", "fee_type"))


def upgrade() -> None:
    connection = op.get_bind()
    for table_name, column_name, _column_type in _REQUIRED_VALUES:
        null_count = connection.execute(
            sa.text(f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" IS NULL')
        ).scalar_one()
        if null_count:
            raise RuntimeError(
                f"Cannot make {table_name}.{column_name} NOT NULL: "
                f"{null_count} existing row(s) have no value. Review/backfill them before retrying."
            )

    for table_name, column_name in _NONEMPTY_CATEGORIES:
        blank_count = connection.execute(
            sa.text(
                f'SELECT count(*) FROM "{table_name}" '
                f'WHERE length(btrim("{column_name}")) = 0'
            )
        ).scalar_one()
        if blank_count:
            raise RuntimeError(
                f"Cannot add the non-empty check for {table_name}.{column_name}: "
                f"{blank_count} existing row(s) have a blank value. Review them before retrying."
            )

    for table_name, column_name, column_type in _REQUIRED_VALUES:
        op.alter_column(
            table_name,
            column_name,
            existing_type=column_type,
            existing_nullable=True,
            nullable=False,
        )

    op.create_check_constraint(
        op.f("ck_formation_kind_non_empty"),
        "formation",
        "length(btrim(kind)) > 0",
    )
    op.create_check_constraint(
        op.f("ck_tuition_fee_fee_type_non_empty"),
        "tuition_fee",
        "length(btrim(fee_type)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_tuition_fee_fee_type_non_empty"), "tuition_fee", type_="check"
    )
    op.drop_constraint(
        op.f("ck_formation_kind_non_empty"), "formation", type_="check"
    )
    for table_name, column_name, column_type in reversed(_REQUIRED_VALUES):
        op.alter_column(
            table_name,
            column_name,
            existing_type=column_type,
            existing_nullable=False,
            nullable=True,
        )
