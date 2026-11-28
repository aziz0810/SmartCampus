"""SA-14: official documents, versions, change history and sync jobs.

Adds document, document_version, document_event and document_sync_job.
Passages/embeddings (SA-45/46) are not created here; they will reference
document_version.id. Existing tables are not modified.

Revision ID: b4d6f8a0c2e3
Revises: a3c5e7f9b1d2
Create Date: 2026-11-28 15:50:36.356873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b4d6f8a0c2e3'
down_revision: Union[str, Sequence[str], None] = 'a3c5e7f9b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('document',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('institution_id', sa.Integer(), nullable=False),
    sa.Column('formation_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('language', sa.String(length=10), server_default='fr', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('admission', 'programme', 'reglement', 'frais', 'calendrier', 'autre')", name=op.f('ck_document_category_allowed')),
    sa.CheckConstraint("status <> 'published' OR published_at IS NOT NULL", name=op.f('ck_document_published_has_date')),
    sa.CheckConstraint("status <> 'withdrawn' OR withdrawn_at IS NOT NULL", name=op.f('ck_document_withdrawn_has_date')),
    sa.CheckConstraint("status IN ('draft', 'published', 'withdrawn')", name=op.f('ck_document_status_allowed')),
    sa.ForeignKeyConstraint(['created_by_id'], ['app_user.id'], name=op.f('fk_document_created_by_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['formation_id'], ['formation.id'], name=op.f('fk_document_formation_id_formation'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_document_institution_id_institution'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document'))
    )
    op.create_index(op.f('ix_document_created_by_id'), 'document', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_document_formation_id'), 'document', ['formation_id'], unique=False)
    op.create_index('ix_document_institution_status', 'document', ['institution_id', 'status'], unique=False)
    op.create_table('document_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('version_number', sa.SmallInteger(), nullable=False),
    sa.Column('is_current', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('checksum_sha256', sa.String(length=64), nullable=False),
    sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
    sa.Column('extraction_status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('extraction_note', sa.Text(), nullable=True),
    sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("extraction_status IN ('pending', 'ok', 'partial', 'failed')", name=op.f('ck_document_version_extraction_status_allowed')),
    sa.CheckConstraint("mime_type IN ('application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')", name=op.f('ck_document_version_mime_type_allowed')),
    sa.CheckConstraint('char_length(checksum_sha256) = 64', name=op.f('ck_document_version_checksum_length')),
    sa.CheckConstraint('size_bytes > 0', name=op.f('ck_document_version_size_positive')),
    sa.CheckConstraint('version_number > 0', name=op.f('ck_document_version_version_number_positive')),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_document_version_document_id_document'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['app_user.id'], name=op.f('fk_document_version_uploaded_by_id_app_user'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_version')),
    sa.UniqueConstraint('document_id', 'version_number', name='uq_document_version_document_number'),
    sa.UniqueConstraint('storage_key', name=op.f('uq_document_version_storage_key'))
    )
    op.create_index(op.f('ix_document_version_checksum_sha256'), 'document_version', ['checksum_sha256'], unique=False)
    op.create_index(op.f('ix_document_version_document_id'), 'document_version', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_version_uploaded_by_id'), 'document_version', ['uploaded_by_id'], unique=False)
    op.create_index('uq_document_version_one_current', 'document_version', ['document_id'], unique=True, postgresql_where=sa.text('is_current'))
    op.create_table('document_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("event_type IN ('created', 'updated', 'version_added', 'published', 'withdrawn')", name=op.f('ck_document_event_event_type_allowed')),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_document_event_actor_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_document_event_document_id_document'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['version_id'], ['document_version.id'], name=op.f('fk_document_event_version_id_document_version'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_event'))
    )
    op.create_index(op.f('ix_document_event_actor_id'), 'document_event', ['actor_id'], unique=False)
    op.create_index('ix_document_event_document_occurred', 'document_event', ['document_id', 'occurred_at'], unique=False)
    op.create_index(op.f('ix_document_event_version_id'), 'document_event', ['version_id'], unique=False)
    op.create_table('document_sync_job',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('passages_count', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("action = 'remove' OR version_id IS NOT NULL", name=op.f('ck_document_sync_job_indexing_has_version')),
    sa.CheckConstraint("action IN ('index', 'reindex', 'remove')", name=op.f('ck_document_sync_job_action_allowed')),
    sa.CheckConstraint("status <> 'done' OR finished_at IS NOT NULL", name=op.f('ck_document_sync_job_done_has_finish_date')),
    sa.CheckConstraint("status IN ('pending', 'running', 'done', 'failed')", name=op.f('ck_document_sync_job_status_allowed')),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_document_sync_job_attempts_non_negative')),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_document_sync_job_document_id_document'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['event_id'], ['document_event.id'], name=op.f('fk_document_sync_job_event_id_document_event'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['version_id'], ['document_version.id'], name=op.f('fk_document_sync_job_version_id_document_version'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_sync_job')),
    sa.UniqueConstraint('event_id', name=op.f('uq_document_sync_job_event_id'))
    )
    op.create_index(op.f('ix_document_sync_job_document_id'), 'document_sync_job', ['document_id'], unique=False)
    op.create_index('ix_document_sync_job_status_created', 'document_sync_job', ['status', 'created_at'], unique=False)
    op.create_index(op.f('ix_document_sync_job_version_id'), 'document_sync_job', ['version_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_sync_job_version_id'), table_name='document_sync_job')
    op.drop_index('ix_document_sync_job_status_created', table_name='document_sync_job')
    op.drop_index(op.f('ix_document_sync_job_document_id'), table_name='document_sync_job')
    op.drop_table('document_sync_job')
    op.drop_index(op.f('ix_document_event_version_id'), table_name='document_event')
    op.drop_index('ix_document_event_document_occurred', table_name='document_event')
    op.drop_index(op.f('ix_document_event_actor_id'), table_name='document_event')
    op.drop_table('document_event')
    op.drop_index('uq_document_version_one_current', table_name='document_version', postgresql_where=sa.text('is_current'))
    op.drop_index(op.f('ix_document_version_uploaded_by_id'), table_name='document_version')
    op.drop_index(op.f('ix_document_version_document_id'), table_name='document_version')
    op.drop_index(op.f('ix_document_version_checksum_sha256'), table_name='document_version')
    op.drop_table('document_version')
    op.drop_index('ix_document_institution_status', table_name='document')
    op.drop_index(op.f('ix_document_formation_id'), table_name='document')
    op.drop_index(op.f('ix_document_created_by_id'), table_name='document')
    op.drop_table('document')
