"""SA-13 integration tests: candidates, conversations and applications on PostgreSQL.

Rows are fictional demo rows inside a transaction that is always rolled back.
The downgrade round trip only runs on an empty database.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pg_helpers import downgrade_round_trip

SA13_TABLES = (
    "candidate_profile", "staff_permission", "conversation", "conversation_message",
    "preregistration", "equivalence_request", "appointment_slot", "appointment",
    "interview", "request_status_history",
)
PREVIOUS_REVISION = "b4d6f8a0c2e3"  # either parent of the merge works
SOURCE_NOTE = "SA-13 test (fictional demo row)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class World:
    """Fictional institution, formation, candidate and responsable."""

    def __init__(self, db: Session):
        from app.models import AppUser, Formation, Institution, Role

        self.db = db
        self.institution = Institution(code="SA13-TEST", name="Institution de test SA-13")
        roles = {r.code: r for r in db.scalars(select(Role)).all()}
        for code in ("candidat", "responsable"):
            if code not in roles:
                roles[code] = Role(code=code, name=code.title())
                db.add(roles[code])
        db.add(self.institution)
        db.flush()
        self.formation = Formation(
            institution_id=self.institution.id, code="sa13-ing-test",
            name="Cycle ingénieur (test)", kind="ingenieur", is_demo=True,
            source_note=SOURCE_NOTE,
        )
        self.candidate = AppUser(
            email="candidat.sa13@example.test", full_name="Candidat (test)",
            password_hash="not-a-real-hash", role_id=roles["candidat"].id,
        )
        self.staff = AppUser(
            email="responsable.sa13@example.test", full_name="Responsable (test)",
            password_hash="not-a-real-hash", role_id=roles["responsable"].id,
            institution_id=self.institution.id,
        )
        db.add_all([self.formation, self.candidate, self.staff])
        db.flush()

    def preregistration(self, **overrides):
        from app.models import Preregistration

        values = {
            "candidate_id": self.candidate.id, "formation_id": self.formation.id,
            "academic_year": "2026-2027", "is_demo": True, "source_note": SOURCE_NOTE,
        } | overrides
        row = Preregistration(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def slot(self, start: datetime | None = None):
        from app.models import AppointmentSlot

        start = start or _now() + timedelta(days=3)
        row = AppointmentSlot(
            institution_id=self.institution.id, staff_user_id=self.staff.id,
            starts_at=start, ends_at=start + timedelta(minutes=30),
        )
        self.db.add(row)
        self.db.flush()
        return row


@pytest.fixture
def world(session):
    return World(session)


def _expect(session, constraint: str):
    with pytest.raises(IntegrityError, match=constraint):
        session.flush()


def test_tables_exist_and_heads_are_merged(engine):
    assert set(SA13_TABLES) <= set(inspect(engine).get_table_names())
    columns = {c["name"] for c in inspect(engine).get_columns("visitor_session")}
    assert "claimed_by_user_id" in columns  # SA-28/29 branch is applied too


def test_profile_permissions_and_conversation(session, world):
    from app.models import (
        CandidateProfile, Conversation, ConversationMessage, StaffPermission, VisitorSession,
    )

    session.add(CandidateProfile(
        user_id=world.candidate.id, academic_level="terminale mathématiques",
        favorite_subjects=["mathématiques", "physique"], interests=["informatique"],
        career_goal="ingénieur", preferred_language="français", is_demo=True,
    ))
    session.add(StaffPermission(
        user_id=world.staff.id, permission="entretien", institution_id=world.institution.id,
    ))
    visitor = VisitorSession(
        id=uuid.uuid4(), token_hash="a" * 64, expires_at=_now() + timedelta(hours=1),
        claimed_by_user_id=world.candidate.id,
    )
    session.add(visitor)
    session.flush()
    conversation = Conversation(candidate_id=world.candidate.id, visitor_session_id=visitor.id)
    session.add(conversation)
    session.flush()
    session.add_all([
        ConversationMessage(conversation_id=conversation.id, role="user",
                            content="nheb informatique, prépa wala licence ?",
                            detected_language="arabizi", intent="comparison"),
        ConversationMessage(conversation_id=conversation.id, role="assistant",
                            content="Voici les deux voies…", sources=[{"document_id": 1, "page": 3}]),
    ])
    session.flush()

    # The guest session expires and is purged: the conversation stays.
    session.delete(visitor)
    session.flush()
    session.refresh(conversation)
    assert conversation.visitor_session_id is None
    profile = session.scalars(select(CandidateProfile)).one()
    assert profile.favorite_subjects == ["mathématiques", "physique"]


def test_permission_is_unique_and_checked(session, world):
    from app.models import StaffPermission

    values = {"user_id": world.staff.id, "institution_id": world.institution.id}
    session.add(StaffPermission(permission="academique", **values))
    session.flush()
    session.add(StaffPermission(permission="academique", **values))
    _expect(session, "uq_staff_permission_user_permission_institution")
    session.rollback()

    world = World(session)
    session.add(StaffPermission(permission="superadmin", user_id=world.staff.id,
                                institution_id=world.institution.id))
    _expect(session, "ck_staff_permission_permission_allowed")


def test_preregistration_full_path(session, world):
    from app.models import Appointment, Interview, RequestStatusHistory

    pre = world.preregistration()
    session.refresh(pre)
    assert pre.status == "BROUILLON"

    def move(to: str, reason: str | None = None, actor=None):
        session.add(RequestStatusHistory(
            preregistration_id=pre.id, from_status=pre.status, to_status=to,
            actor_id=actor.id if actor else None, reason=reason,
        ))
        pre.status = to
        session.flush()

    pre.consent_at = pre.submitted_at = _now()
    move("SOUMISE", actor=world.candidate)
    move("QCM_EN_ATTENTE")
    move("QCM_TERMINE")
    move("ENTRETIEN")

    slot = world.slot()
    appointment = Appointment(candidate_id=world.candidate.id, preregistration_id=pre.id,
                              slot_id=slot.id, status="CONFIRME", confirmed_at=_now())
    session.add(appointment)
    session.flush()
    interview = Interview(preregistration_id=pre.id, appointment_id=appointment.id,
                          interviewer_id=world.staff.id, status="PRET",
                          preparation_summary="Profil solide en mathématiques (test).")
    session.add(interview)
    session.flush()
    interview.status, interview.completed_at = "REALISE", _now()
    interview.observations, interview.result = "Bonne motivation (test).", "FAVORABLE"
    appointment.status = "REALISE"
    session.flush()

    pre.decided_at = _now()
    move("ADMISE", reason="Avis FAVORABLE de l'entretien", actor=world.staff)
    move("INSCRITE", actor=world.staff)

    history = session.scalars(
        select(RequestStatusHistory.to_status)
        .where(RequestStatusHistory.preregistration_id == pre.id)
        .order_by(RequestStatusHistory.id)
    ).all()
    assert history == ["SOUMISE", "QCM_EN_ATTENTE", "QCM_TERMINE", "ENTRETIEN", "ADMISE", "INSCRITE"]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": "ENVOYEE"}, "ck_preregistration_status_allowed"),
        ({"status": "SOUMISE"}, "ck_preregistration_submitted_with_consent"),
        ({"status": "ADMISE", "consent_at": "now", "submitted_at": "now"},
         "ck_preregistration_decision_has_date"),
        ({"status": "REFUSEE", "consent_at": "now", "submitted_at": "now", "decided_at": "now"},
         "ck_preregistration_refusal_has_reason"),
    ],
    ids=["bad-status", "submitted-without-consent", "admitted-without-date", "refused-without-reason"],
)
def test_preregistration_checks(session, world, overrides, constraint):
    from app.models import Preregistration

    values = {k: (_now() if v == "now" else v) for k, v in overrides.items()}
    session.add(Preregistration(candidate_id=world.candidate.id,
                                formation_id=world.formation.id, **values))
    _expect(session, constraint)


def test_one_active_preregistration_per_formation(session, world):
    from app.models import Preregistration

    world.preregistration()
    session.add(Preregistration(candidate_id=world.candidate.id, formation_id=world.formation.id))
    _expect(session, "uq_preregistration_one_active")
    session.rollback()

    # A withdrawn request does not block a new one ("409 si doublon actif").
    world = World(session)
    world.preregistration(status="ABANDONNEE")
    world.preregistration()


def test_equivalence_decision_needs_reason(session, world):
    from app.models import EquivalenceRequest, RequestStatusHistory

    request = EquivalenceRequest(candidate_id=world.candidate.id,
                                 target_formation_id=world.formation.id,
                                 target_entry_year=2, previous_institution="Université (test)",
                                 is_demo=True)
    session.add(request)
    session.flush()
    request.status, request.consent_at, request.submitted_at = "SOUMISE", _now(), _now()
    session.flush()
    for status in ("EN_VERIFICATION", "INCOMPLETE", "SOUMISE", "EN_VERIFICATION", "EN_EVALUATION"):
        session.add(RequestStatusHistory(equivalence_request_id=request.id,
                                         from_status=request.status, to_status=status))
        request.status = status
        session.flush()

    request.status = "PARTIELLE"
    _expect(session, "ck_equivalence_request_decision_complete")
    session.rollback()


def test_equivalence_partial_decision(session, world):
    from app.models import EquivalenceRequest

    session.add(EquivalenceRequest(
        candidate_id=world.candidate.id, target_formation_id=world.formation.id,
        status="PARTIELLE", consent_at=_now(), submitted_at=_now(), decided_at=_now(),
        decided_by_id=world.staff.id, decision_reason="Deux modules validés (test).",
    ))
    session.flush()


def test_slot_cannot_be_double_booked_and_rescheduling(session, world):
    from app.models import Appointment

    slot = world.slot()
    first = Appointment(candidate_id=world.candidate.id, slot_id=slot.id)
    session.add(first)
    session.flush()
    session.add(Appointment(candidate_id=world.candidate.id, slot_id=slot.id))
    _expect(session, "uq_appointment_one_active_per_slot")
    session.rollback()

    world = World(session)
    slot = world.slot()
    missed = Appointment(candidate_id=world.candidate.id, slot_id=slot.id,
                         status="ABSENT", confirmed_at=_now())
    session.add(missed)
    session.flush()
    new_slot = world.slot(_now() + timedelta(days=5))
    session.add(Appointment(candidate_id=world.candidate.id, slot_id=new_slot.id,
                            previous_appointment_id=missed.id))
    session.flush()  # "Nouveau PROPOSE" after an absence


@pytest.mark.parametrize(
    ("factory", "constraint"),
    [
        ("slot_end_before_start", "ck_appointment_slot_ends_after_start"),
        ("cancel_without_date", "ck_appointment_cancelled_has_date"),
        ("confirm_without_date", "ck_appointment_confirmed_has_date"),
    ],
)
def test_appointment_checks(session, world, factory, constraint):
    from app.models import Appointment, AppointmentSlot

    if factory == "slot_end_before_start":
        start = _now()
        session.add(AppointmentSlot(institution_id=world.institution.id,
                                    staff_user_id=world.staff.id,
                                    starts_at=start, ends_at=start - timedelta(minutes=1)))
    else:
        slot = world.slot()
        status = "ANNULE" if factory == "cancel_without_date" else "CONFIRME"
        session.add(Appointment(candidate_id=world.candidate.id, slot_id=slot.id, status=status))
    _expect(session, constraint)


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "PRET", "result": "FAVORABLE"}, "ck_interview_result_only_when_done"),
        ({"status": "REALISE"}, "ck_interview_done_has_observations"),
        ({"result": "PEUT_ETRE"}, "ck_interview_result_allowed"),
    ],
    ids=["result-before-done", "done-without-observations", "bad-result"],
)
def test_interview_checks(session, world, values, constraint):
    from app.models import Interview

    pre = world.preregistration()
    session.add(Interview(preregistration_id=pre.id, **values))
    _expect(session, constraint)


def test_history_has_exactly_one_target(session, world):
    from app.models import RequestStatusHistory

    session.add(RequestStatusHistory(to_status="SOUMISE"))
    _expect(session, "ck_request_status_history_exactly_one_target")


def test_downgrade_then_upgrade(engine):
    downgrade_round_trip(engine, PREVIOUS_REVISION, SA13_TABLES)
