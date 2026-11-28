"""SA-13: candidates, responsables, conversations and applications.

Adds candidate_profile, staff_permission, conversation, conversation_message,
preregistration, equivalence_request, appointment_slot, appointment,
interview and request_status_history. Existing tables are not modified.

Also merges the two migration heads: a1b2c3d4e5f6 (SA-28/29 auth) and
b4d6f8a0c2e3 (SA-14 documents) both followed 9b20a2c83f71.

Revision ID: c5e7a9b1d3f4
Revises: a1b2c3d4e5f6, b4d6f8a0c2e3
Create Date: 2026-11-28 16:15:52.300891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5e7a9b1d3f4'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'b4d6f8a0c2e3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('appointment_slot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('institution_id', sa.Integer(), nullable=False),
    sa.Column('staff_user_id', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('mode', sa.String(length=20), server_default='presentiel', nullable=False),
    sa.Column('is_open', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("mode IN ('presentiel', 'visio')", name=op.f('ck_appointment_slot_mode_allowed')),
    sa.CheckConstraint('ends_at > starts_at', name=op.f('ck_appointment_slot_ends_after_start')),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_appointment_slot_institution_id_institution'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['staff_user_id'], ['app_user.id'], name=op.f('fk_appointment_slot_staff_user_id_app_user'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appointment_slot')),
    sa.UniqueConstraint('staff_user_id', 'starts_at', name='uq_appointment_slot_staff_start')
    )
    op.create_index(op.f('ix_appointment_slot_institution_id'), 'appointment_slot', ['institution_id'], unique=False)
    op.create_index(op.f('ix_appointment_slot_staff_user_id'), 'appointment_slot', ['staff_user_id'], unique=False)
    op.create_table('candidate_profile',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('academic_level', sa.String(length=255), nullable=True),
    sa.Column('qualification_id', sa.Integer(), nullable=True),
    sa.Column('favorite_subjects', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('interests', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('career_goal', sa.Text(), nullable=True),
    sa.Column('constraints', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('preferred_language', sa.String(length=20), nullable=True),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['qualification_id'], ['qualification.id'], name=op.f('fk_candidate_profile_qualification_id_qualification'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_candidate_profile_user_id_app_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_candidate_profile')),
    sa.UniqueConstraint('user_id', name=op.f('uq_candidate_profile_user_id'))
    )
    op.create_index(op.f('ix_candidate_profile_qualification_id'), 'candidate_profile', ['qualification_id'], unique=False)
    op.create_table('equivalence_request',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('target_formation_id', sa.Integer(), nullable=False),
    sa.Column('target_entry_year', sa.SmallInteger(), nullable=True),
    sa.Column('qualification_id', sa.Integer(), nullable=True),
    sa.Column('previous_institution', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='BROUILLON', nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by_id', sa.Integer(), nullable=True),
    sa.Column('decision_reason', sa.Text(), nullable=True),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status = 'BROUILLON' OR (consent_at IS NOT NULL AND submitted_at IS NOT NULL)", name=op.f('ck_equivalence_request_submitted_with_consent')),
    sa.CheckConstraint("status IN ('BROUILLON', 'SOUMISE', 'EN_VERIFICATION', 'INCOMPLETE', 'EN_EVALUATION', 'ACCEPTEE', 'PARTIELLE', 'REFUSEE')", name=op.f('ck_equivalence_request_status_allowed')),
    sa.CheckConstraint("status NOT IN ('ACCEPTEE', 'PARTIELLE', 'REFUSEE') OR (decided_at IS NOT NULL AND decided_by_id IS NOT NULL AND decision_reason IS NOT NULL)", name=op.f('ck_equivalence_request_decision_complete')),
    sa.CheckConstraint('target_entry_year > 0', name=op.f('ck_equivalence_request_target_entry_year_positive')),
    sa.ForeignKeyConstraint(['candidate_id'], ['app_user.id'], name=op.f('fk_equivalence_request_candidate_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['app_user.id'], name=op.f('fk_equivalence_request_decided_by_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['qualification_id'], ['qualification.id'], name=op.f('fk_equivalence_request_qualification_id_qualification'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['target_formation_id'], ['formation.id'], name=op.f('fk_equivalence_request_target_formation_id_formation'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_equivalence_request'))
    )
    op.create_index(op.f('ix_equivalence_request_candidate_id'), 'equivalence_request', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_equivalence_request_decided_by_id'), 'equivalence_request', ['decided_by_id'], unique=False)
    op.create_index(op.f('ix_equivalence_request_qualification_id'), 'equivalence_request', ['qualification_id'], unique=False)
    op.create_index(op.f('ix_equivalence_request_target_formation_id'), 'equivalence_request', ['target_formation_id'], unique=False)
    op.create_index('uq_equivalence_request_one_active', 'equivalence_request', ['candidate_id', 'target_formation_id'], unique=True, postgresql_where=sa.text("status NOT IN ('ACCEPTEE', 'PARTIELLE', 'REFUSEE')"))
    op.create_table('staff_permission',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('permission', sa.String(length=20), nullable=False),
    sa.Column('institution_id', sa.Integer(), nullable=False),
    sa.Column('granted_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("permission IN ('academique', 'entretien', 'direction', 'administration')", name=op.f('ck_staff_permission_permission_allowed')),
    sa.ForeignKeyConstraint(['granted_by_id'], ['app_user.id'], name=op.f('fk_staff_permission_granted_by_id_app_user'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['institution_id'], ['institution.id'], name=op.f('fk_staff_permission_institution_id_institution'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_staff_permission_user_id_app_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_permission')),
    sa.UniqueConstraint('user_id', 'permission', 'institution_id', name='uq_staff_permission_user_permission_institution')
    )
    op.create_index(op.f('ix_staff_permission_institution_id'), 'staff_permission', ['institution_id'], unique=False)
    op.create_index(op.f('ix_staff_permission_user_id'), 'staff_permission', ['user_id'], unique=False)
    op.create_table('conversation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('visitor_session_id', sa.Uuid(), nullable=True),
    sa.Column('channel', sa.String(length=10), server_default='texte', nullable=False),
    sa.Column('language', sa.String(length=20), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('texte', 'audio')", name=op.f('ck_conversation_channel_allowed')),
    sa.ForeignKeyConstraint(['candidate_id'], ['app_user.id'], name=op.f('fk_conversation_candidate_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['visitor_session_id'], ['visitor_session.id'], name=op.f('fk_conversation_visitor_session_id_visitor_session'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversation')),
    sa.UniqueConstraint('visitor_session_id', name=op.f('uq_conversation_visitor_session_id'))
    )
    op.create_index(op.f('ix_conversation_candidate_id'), 'conversation', ['candidate_id'], unique=False)
    op.create_table('preregistration',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('formation_id', sa.Integer(), nullable=False),
    sa.Column('specialty_id', sa.Integer(), nullable=True),
    sa.Column('academic_year', sa.String(length=9), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='BROUILLON', nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_reason', sa.Text(), nullable=True),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status <> 'REFUSEE' OR decision_reason IS NOT NULL", name=op.f('ck_preregistration_refusal_has_reason')),
    sa.CheckConstraint("status IN ('BROUILLON', 'ABANDONNEE') OR (consent_at IS NOT NULL AND submitted_at IS NOT NULL)", name=op.f('ck_preregistration_submitted_with_consent')),
    sa.CheckConstraint("status IN ('BROUILLON', 'SOUMISE', 'QCM_EN_ATTENTE', 'QCM_TERMINE', 'ENTRETIEN', 'ADMISE', 'REFUSEE', 'INSCRITE', 'ABANDONNEE')", name=op.f('ck_preregistration_status_allowed')),
    sa.CheckConstraint("status NOT IN ('ADMISE', 'REFUSEE', 'INSCRITE') OR decided_at IS NOT NULL", name=op.f('ck_preregistration_decision_has_date')),
    sa.ForeignKeyConstraint(['candidate_id'], ['app_user.id'], name=op.f('fk_preregistration_candidate_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['formation_id'], ['formation.id'], name=op.f('fk_preregistration_formation_id_formation'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['specialty_id'], ['specialty.id'], name=op.f('fk_preregistration_specialty_id_specialty'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_preregistration'))
    )
    op.create_index(op.f('ix_preregistration_candidate_id'), 'preregistration', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_preregistration_formation_id'), 'preregistration', ['formation_id'], unique=False)
    op.create_index(op.f('ix_preregistration_specialty_id'), 'preregistration', ['specialty_id'], unique=False)
    op.create_index('uq_preregistration_one_active', 'preregistration', ['candidate_id', 'formation_id'], unique=True, postgresql_where=sa.text("status NOT IN ('REFUSEE', 'ABANDONNEE')"))
    op.create_table('appointment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('preregistration_id', sa.Integer(), nullable=True),
    sa.Column('slot_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='PROPOSE', nullable=False),
    sa.Column('previous_appointment_id', sa.Integer(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status <> 'ANNULE' OR cancelled_at IS NOT NULL", name=op.f('ck_appointment_cancelled_has_date')),
    sa.CheckConstraint("status IN ('PROPOSE', 'CONFIRME', 'REALISE', 'ANNULE', 'ABSENT')", name=op.f('ck_appointment_status_allowed')),
    sa.CheckConstraint("status NOT IN ('CONFIRME', 'REALISE') OR confirmed_at IS NOT NULL", name=op.f('ck_appointment_confirmed_has_date')),
    sa.CheckConstraint('previous_appointment_id <> id', name=op.f('ck_appointment_not_own_previous')),
    sa.ForeignKeyConstraint(['candidate_id'], ['app_user.id'], name=op.f('fk_appointment_candidate_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['preregistration_id'], ['preregistration.id'], name=op.f('fk_appointment_preregistration_id_preregistration'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['previous_appointment_id'], ['appointment.id'], name=op.f('fk_appointment_previous_appointment_id_appointment'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['slot_id'], ['appointment_slot.id'], name=op.f('fk_appointment_slot_id_appointment_slot'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appointment')),
    sa.UniqueConstraint('previous_appointment_id', name=op.f('uq_appointment_previous_appointment_id'))
    )
    op.create_index(op.f('ix_appointment_candidate_id'), 'appointment', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_appointment_preregistration_id'), 'appointment', ['preregistration_id'], unique=False)
    op.create_index(op.f('ix_appointment_slot_id'), 'appointment', ['slot_id'], unique=False)
    op.create_index('uq_appointment_one_active_per_slot', 'appointment', ['slot_id'], unique=True, postgresql_where=sa.text("status IN ('PROPOSE', 'CONFIRME')"))
    op.create_table('conversation_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('detected_language', sa.String(length=20), nullable=True),
    sa.Column('intent', sa.String(length=30), nullable=True),
    sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f('ck_conversation_message_role_allowed')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id'], name=op.f('fk_conversation_message_conversation_id_conversation'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversation_message'))
    )
    op.create_index('ix_conversation_message_conversation_created', 'conversation_message', ['conversation_id', 'created_at', 'id'], unique=False)
    op.create_table('interview',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('preregistration_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('interviewer_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='A_PREPARER', nullable=False),
    sa.Column('preparation_summary', sa.Text(), nullable=True),
    sa.Column('observations', sa.Text(), nullable=True),
    sa.Column('result', sa.String(length=20), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("result IS NULL OR result IN ('FAVORABLE', 'COMPLEMENT_REQUIS', 'DEFAVORABLE')", name=op.f('ck_interview_result_allowed')),
    sa.CheckConstraint("result IS NULL OR status = 'REALISE'", name=op.f('ck_interview_result_only_when_done')),
    sa.CheckConstraint("status <> 'REALISE' OR (completed_at IS NOT NULL AND observations IS NOT NULL)", name=op.f('ck_interview_done_has_observations')),
    sa.CheckConstraint("status IN ('A_PREPARER', 'PRET', 'REALISE')", name=op.f('ck_interview_status_allowed')),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], name=op.f('fk_interview_appointment_id_appointment'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['interviewer_id'], ['app_user.id'], name=op.f('fk_interview_interviewer_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['preregistration_id'], ['preregistration.id'], name=op.f('fk_interview_preregistration_id_preregistration'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interview')),
    sa.UniqueConstraint('preregistration_id', name=op.f('uq_interview_preregistration_id'))
    )
    op.create_index(op.f('ix_interview_appointment_id'), 'interview', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_interview_interviewer_id'), 'interview', ['interviewer_id'], unique=False)
    op.create_table('request_status_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('preregistration_id', sa.Integer(), nullable=True),
    sa.Column('equivalence_request_id', sa.Integer(), nullable=True),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('interview_id', sa.Integer(), nullable=True),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('num_nonnulls(preregistration_id, equivalence_request_id, appointment_id, interview_id) = 1', name=op.f('ck_request_status_history_exactly_one_target')),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_request_status_history_actor_id_app_user'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], name=op.f('fk_request_status_history_appointment_id_appointment'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equivalence_request_id'], ['equivalence_request.id'], name='fk_request_status_history_equivalence_request', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['interview_id'], ['interview.id'], name=op.f('fk_request_status_history_interview_id_interview'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['preregistration_id'], ['preregistration.id'], name=op.f('fk_request_status_history_preregistration_id_preregistration'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_request_status_history'))
    )
    op.create_index(op.f('ix_request_status_history_actor_id'), 'request_status_history', ['actor_id'], unique=False)
    op.create_index(op.f('ix_request_status_history_appointment_id'), 'request_status_history', ['appointment_id'], unique=False)
    op.create_index(op.f('ix_request_status_history_equivalence_request_id'), 'request_status_history', ['equivalence_request_id'], unique=False)
    op.create_index(op.f('ix_request_status_history_interview_id'), 'request_status_history', ['interview_id'], unique=False)
    op.create_index(op.f('ix_request_status_history_preregistration_id'), 'request_status_history', ['preregistration_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_request_status_history_preregistration_id'), table_name='request_status_history')
    op.drop_index(op.f('ix_request_status_history_interview_id'), table_name='request_status_history')
    op.drop_index(op.f('ix_request_status_history_equivalence_request_id'), table_name='request_status_history')
    op.drop_index(op.f('ix_request_status_history_appointment_id'), table_name='request_status_history')
    op.drop_index(op.f('ix_request_status_history_actor_id'), table_name='request_status_history')
    op.drop_table('request_status_history')
    op.drop_index(op.f('ix_interview_interviewer_id'), table_name='interview')
    op.drop_index(op.f('ix_interview_appointment_id'), table_name='interview')
    op.drop_table('interview')
    op.drop_index('ix_conversation_message_conversation_created', table_name='conversation_message')
    op.drop_table('conversation_message')
    op.drop_index('uq_appointment_one_active_per_slot', table_name='appointment', postgresql_where=sa.text("status IN ('PROPOSE', 'CONFIRME')"))
    op.drop_index(op.f('ix_appointment_slot_id'), table_name='appointment')
    op.drop_index(op.f('ix_appointment_preregistration_id'), table_name='appointment')
    op.drop_index(op.f('ix_appointment_candidate_id'), table_name='appointment')
    op.drop_table('appointment')
    op.drop_index('uq_preregistration_one_active', table_name='preregistration', postgresql_where=sa.text("status NOT IN ('REFUSEE', 'ABANDONNEE')"))
    op.drop_index(op.f('ix_preregistration_specialty_id'), table_name='preregistration')
    op.drop_index(op.f('ix_preregistration_formation_id'), table_name='preregistration')
    op.drop_index(op.f('ix_preregistration_candidate_id'), table_name='preregistration')
    op.drop_table('preregistration')
    op.drop_index(op.f('ix_conversation_candidate_id'), table_name='conversation')
    op.drop_table('conversation')
    op.drop_index(op.f('ix_staff_permission_user_id'), table_name='staff_permission')
    op.drop_index(op.f('ix_staff_permission_institution_id'), table_name='staff_permission')
    op.drop_table('staff_permission')
    op.drop_index('uq_equivalence_request_one_active', table_name='equivalence_request', postgresql_where=sa.text("status NOT IN ('ACCEPTEE', 'PARTIELLE', 'REFUSEE')"))
    op.drop_index(op.f('ix_equivalence_request_target_formation_id'), table_name='equivalence_request')
    op.drop_index(op.f('ix_equivalence_request_qualification_id'), table_name='equivalence_request')
    op.drop_index(op.f('ix_equivalence_request_decided_by_id'), table_name='equivalence_request')
    op.drop_index(op.f('ix_equivalence_request_candidate_id'), table_name='equivalence_request')
    op.drop_table('equivalence_request')
    op.drop_index(op.f('ix_candidate_profile_qualification_id'), table_name='candidate_profile')
    op.drop_table('candidate_profile')
    op.drop_index(op.f('ix_appointment_slot_staff_user_id'), table_name='appointment_slot')
    op.drop_index(op.f('ix_appointment_slot_institution_id'), table_name='appointment_slot')
    op.drop_table('appointment_slot')
