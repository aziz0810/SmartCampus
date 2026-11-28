"""SA-14 integration tests: documents, versions, history and sync jobs on PostgreSQL.

Rows are fictional demo rows inside a transaction that is always rolled back.
The downgrade round trip only runs on an empty database.
"""

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pg_helpers import downgrade_round_trip

SA14_TABLES = ("document", "document_version", "document_event", "document_sync_job")
PREVIOUS_REVISION = "a3c5e7f9b1d2"
SOURCE_NOTE = "SA-14 test (fictional demo row)"
PDF = "application/pdf"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _checksum(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _setup(db: Session):
    from app.models import AppUser, Document, Institution, Role

    institution = Institution(code="SA14-TEST", name="Institution de test SA-14")
    role = Role(code="sa14_responsable", name="Responsable (test)")
    db.add_all([institution, role])
    db.flush()
    user = AppUser(
        email="responsable.sa14@example.test",
        full_name="Responsable (test)",
        password_hash="not-a-real-hash",
        role_id=role.id,
        institution_id=institution.id,
    )
    db.add(user)
    db.flush()
    document = Document(
        institution_id=institution.id,
        title="Critères d'admission (test)",
        category="admission",
        created_by_id=user.id,
        is_demo=True,
        source_note=SOURCE_NOTE,
    )
    db.add(document)
    db.flush()
    return user, document


def _version(document, number: int, *, current: bool = False, **overrides):
    from app.models import DocumentVersion

    values = {
        "document_id": document.id,
        "version_number": number,
        "is_current": current,
        "storage_key": f"documents/sa14-test/{document.id}/v{number}.pdf",
        "original_filename": f"criteres_v{number}.pdf",
        "mime_type": PDF,
        "size_bytes": 1024,
        "checksum_sha256": _checksum(f"v{number}"),
    } | overrides
    return DocumentVersion(**values)


def test_tables_exist_after_upgrade(engine):
    assert set(SA14_TABLES) <= set(inspect(engine).get_table_names())


def test_document_lifecycle_with_retry(session):
    from app.models import Document, DocumentEvent, DocumentSyncJob

    user, document = _setup(session)
    session.refresh(document)
    assert document.status == "draft" and document.language == "fr"

    v1 = _version(document, 1, current=True, uploaded_by_id=user.id)
    session.add(v1)
    session.flush()
    session.refresh(v1)
    assert v1.extraction_status == "pending"

    # Publish: the status change is recorded, then a job is queued for it.
    document.status = "published"
    document.published_at = _now()
    event = DocumentEvent(
        document_id=document.id, version_id=v1.id, event_type="published",
        actor_id=user.id, details={"reason": "test"},
    )
    session.add(event)
    session.flush()
    job = DocumentSyncJob(
        event_id=event.id, document_id=document.id, version_id=v1.id, action="index"
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    assert (job.status, job.attempts) == ("pending", 0)

    # First attempt fails, the retry reuses the same row.
    job.status, job.attempts, job.started_at = "running", 1, _now()
    session.flush()
    job.status, job.last_error = "failed", "embedding service unavailable (test)"
    session.flush()
    job.status, job.attempts = "running", 2
    session.flush()
    job.status, job.finished_at, job.passages_count = "done", _now(), 12
    session.flush()

    jobs_for_event = session.scalar(
        select(func.count()).select_from(DocumentSyncJob).where(DocumentSyncJob.event_id == event.id)
    )
    assert jobs_for_event == 1
    assert session.get(DocumentSyncJob, job.id).attempts == 2

    # New version: the old one stops being current, history is kept.
    v1.is_current = False
    session.flush()
    v2 = _version(document, 2, current=True, uploaded_by_id=user.id)
    session.add(v2)
    session.flush()
    assert session.get(Document, document.id).status == "published"

    # Withdraw instead of deleting.
    document.status, document.withdrawn_at = "withdrawn", _now()
    session.add(DocumentEvent(document_id=document.id, event_type="withdrawn", actor_id=user.id))
    session.flush()
    remove = DocumentSyncJob(
        event_id=session.scalars(
            select(DocumentEvent.id).where(DocumentEvent.event_type == "withdrawn",
                                           DocumentEvent.document_id == document.id)
        ).one(),
        document_id=document.id,
        action="remove",
    )
    session.add(remove)
    session.flush()


def test_only_one_current_version(session):
    _, document = _setup(session)
    session.add(_version(document, 1, current=True))
    session.flush()
    session.add(_version(document, 2, current=True))
    with pytest.raises(IntegrityError, match="uq_document_version_one_current"):
        session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"category": "divers"}, "ck_document_category_allowed"),
        ({"status": "archived"}, "ck_document_status_allowed"),
        ({"status": "published"}, "ck_document_published_has_date"),
        ({"status": "withdrawn"}, "ck_document_withdrawn_has_date"),
    ],
    ids=["bad-category", "bad-status", "published-without-date", "withdrawn-without-date"],
)
def test_document_checks(session, overrides, constraint):
    from app.models import Document

    _, document = _setup(session)
    values = {
        "institution_id": document.institution_id,
        "title": "Document invalide (test)",
        "category": "autre",
        "is_demo": True,
    } | overrides
    session.add(Document(**values))
    with pytest.raises(IntegrityError, match=constraint):
        session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"mime_type": "image/png"}, "ck_document_version_mime_type_allowed"),
        ({"size_bytes": 0}, "ck_document_version_size_positive"),
        ({"version_number": 0}, "ck_document_version_version_number_positive"),
        ({"checksum_sha256": "abc"}, "ck_document_version_checksum_length"),
        ({"extraction_status": "unknown"}, "ck_document_version_extraction_status_allowed"),
    ],
    ids=["bad-mime", "empty-file", "version-zero", "short-checksum", "bad-extraction-status"],
)
def test_version_checks(session, overrides, constraint):
    _, document = _setup(session)
    session.add(_version(document, 1, **overrides))
    with pytest.raises(IntegrityError, match=constraint):
        session.flush()


def test_version_number_and_storage_key_are_unique(session):
    _, document = _setup(session)
    session.add(_version(document, 1))
    session.flush()
    session.add(_version(document, 1, storage_key="documents/sa14-test/other.pdf"))
    with pytest.raises(IntegrityError, match="uq_document_version_document_number"):
        session.flush()
    session.rollback()

    _, document = _setup(session)
    session.add(_version(document, 1, storage_key="documents/sa14-test/same.pdf"))
    session.flush()
    session.add(_version(document, 2, storage_key="documents/sa14-test/same.pdf"))
    with pytest.raises(IntegrityError, match="uq_document_version_storage_key"):
        session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"action": "index", "version_id": None}, "ck_document_sync_job_indexing_has_version"),
        ({"status": "done"}, "ck_document_sync_job_done_has_finish_date"),
        ({"status": "stuck"}, "ck_document_sync_job_status_allowed"),
        ({"action": "purge"}, "ck_document_sync_job_action_allowed"),
        ({"attempts": -1}, "ck_document_sync_job_attempts_non_negative"),
    ],
    ids=["index-without-version", "done-without-finish", "bad-status", "bad-action", "negative-attempts"],
)
def test_sync_job_checks(session, overrides, constraint):
    from app.models import DocumentEvent, DocumentSyncJob

    _, document = _setup(session)
    version = _version(document, 1, current=True)
    session.add(version)
    session.flush()
    event = DocumentEvent(document_id=document.id, version_id=version.id, event_type="version_added")
    session.add(event)
    session.flush()
    values = {
        "event_id": event.id, "document_id": document.id,
        "version_id": version.id, "action": "reindex",
    } | overrides
    session.add(DocumentSyncJob(**values))
    with pytest.raises(IntegrityError, match=constraint):
        session.flush()


def test_one_job_per_event(session):
    from app.models import DocumentEvent, DocumentSyncJob

    _, document = _setup(session)
    event = DocumentEvent(document_id=document.id, event_type="withdrawn")
    session.add(event)
    session.flush()
    session.add(DocumentSyncJob(event_id=event.id, document_id=document.id, action="remove"))
    session.flush()
    session.add(DocumentSyncJob(event_id=event.id, document_id=document.id, action="remove"))
    with pytest.raises(IntegrityError, match="uq_document_sync_job_event_id"):
        session.flush()


def test_event_type_is_checked(session):
    from app.models import DocumentEvent

    _, document = _setup(session)
    session.add(DocumentEvent(document_id=document.id, event_type="deleted"))
    with pytest.raises(IntegrityError, match="ck_document_event_event_type_allowed"):
        session.flush()


def test_document_with_versions_cannot_be_deleted(session):
    _, document = _setup(session)
    session.add(_version(document, 1, current=True))
    session.flush()
    session.delete(document)
    with pytest.raises(IntegrityError, match="fk_document_version_document_id_document"):
        session.flush()


def test_downgrade_then_upgrade(engine):
    downgrade_round_trip(engine, PREVIOUS_REVISION, SA14_TABLES)
