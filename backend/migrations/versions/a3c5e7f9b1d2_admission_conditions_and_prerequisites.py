"""SA-12: admission conditions, accepted diplomas and prerequisites.

Adds qualification, admission_condition, admission_condition_qualification,
formation_prerequisite and subject_prerequisite. Existing catalogue tables
are not modified.

Revision ID: a3c5e7f9b1d2
Revises: 9b20a2c83f71
Create Date: 2026-11-28 14:51:57.023482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c5e7f9b1d2'
down_revision: Union[str, Sequence[str], None] = '9b20a2c83f71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('qualification',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('field', sa.String(length=255), nullable=True),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('bac', 'prepa', 'licence', 'master', 'ingenieur', 'other')", name=op.f('ck_qualification_kind_allowed')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qualification')),
    sa.UniqueConstraint('code', name=op.f('uq_qualification_code'))
    )
    op.create_table('subject_prerequisite',
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('required_subject_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('subject_id <> required_subject_id', name=op.f('ck_subject_prerequisite_not_self')),
    sa.ForeignKeyConstraint(['required_subject_id'], ['subject.id'], name=op.f('fk_subject_prerequisite_required_subject_id_subject'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], name=op.f('fk_subject_prerequisite_subject_id_subject'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('subject_id', 'required_subject_id', name=op.f('pk_subject_prerequisite'))
    )
    op.create_index(op.f('ix_subject_prerequisite_required_subject_id'), 'subject_prerequisite', ['required_subject_id'], unique=False)
    op.create_table('admission_condition',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('formation_id', sa.Integer(), nullable=False),
    sa.Column('specialty_id', sa.Integer(), nullable=True),
    sa.Column('entry_year', sa.SmallInteger(), nullable=False),
    sa.Column('route', sa.String(length=20), nullable=False),
    sa.Column('min_average', sa.Numeric(precision=4, scale=2), nullable=True),
    sa.Column('selection_method', sa.Text(), nullable=True),
    sa.Column('academic_year', sa.String(length=9), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("route IN ('bac', 'prepa', 'licence', 'master', 'other')", name=op.f('ck_admission_condition_route_allowed')),
    sa.CheckConstraint('entry_year > 0', name=op.f('ck_admission_condition_entry_year_positive')),
    sa.CheckConstraint('min_average >= 0 AND min_average <= 20', name=op.f('ck_admission_condition_min_average_range')),
    sa.ForeignKeyConstraint(['formation_id'], ['formation.id'], name=op.f('fk_admission_condition_formation_id_formation'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialty.id'], name=op.f('fk_admission_condition_specialty_id_specialty'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admission_condition'))
    )
    op.create_index(op.f('ix_admission_condition_formation_id'), 'admission_condition', ['formation_id'], unique=False)
    op.create_index(op.f('ix_admission_condition_specialty_id'), 'admission_condition', ['specialty_id'], unique=False)
    op.create_table('formation_prerequisite',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('formation_id', sa.Integer(), nullable=False),
    sa.Column('specialty_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['formation_id'], ['formation.id'], name=op.f('fk_formation_prerequisite_formation_id_formation'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialty.id'], name=op.f('fk_formation_prerequisite_specialty_id_specialty'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formation_prerequisite'))
    )
    op.create_index(op.f('ix_formation_prerequisite_formation_id'), 'formation_prerequisite', ['formation_id'], unique=False)
    op.create_index(op.f('ix_formation_prerequisite_specialty_id'), 'formation_prerequisite', ['specialty_id'], unique=False)
    op.create_table('admission_condition_qualification',
    sa.Column('admission_condition_id', sa.Integer(), nullable=False),
    sa.Column('qualification_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['admission_condition_id'], ['admission_condition.id'], name='fk_admission_condition_qualification_condition', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['qualification_id'], ['qualification.id'], name='fk_admission_condition_qualification_qualification', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('admission_condition_id', 'qualification_id', name=op.f('pk_admission_condition_qualification'))
    )
    op.create_index(op.f('ix_admission_condition_qualification_qualification_id'), 'admission_condition_qualification', ['qualification_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_admission_condition_qualification_qualification_id'), table_name='admission_condition_qualification')
    op.drop_table('admission_condition_qualification')
    op.drop_index(op.f('ix_formation_prerequisite_specialty_id'), table_name='formation_prerequisite')
    op.drop_index(op.f('ix_formation_prerequisite_formation_id'), table_name='formation_prerequisite')
    op.drop_table('formation_prerequisite')
    op.drop_index(op.f('ix_admission_condition_specialty_id'), table_name='admission_condition')
    op.drop_index(op.f('ix_admission_condition_formation_id'), table_name='admission_condition')
    op.drop_table('admission_condition')
    op.drop_index(op.f('ix_subject_prerequisite_required_subject_id'), table_name='subject_prerequisite')
    op.drop_table('subject_prerequisite')
    op.drop_table('qualification')
