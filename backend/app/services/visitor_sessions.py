import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.visitor import VisitorMessage, VisitorSession


class VisitorSessionNotFound(Exception):
    pass


class VisitorSessionExpired(Exception):
    pass


class InvalidVisitorToken(Exception):
    pass


class VisitorMessageLimitReached(Exception):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_visitor_session(db: Session) -> tuple[VisitorSession, str]:
    now = datetime.now(timezone.utc)
    db.execute(
        delete(VisitorSession)
        .where(VisitorSession.expires_at <= now)
        .execution_options(synchronize_session=False)
    )

    access_token = secrets.token_urlsafe(32)
    session = VisitorSession(
        token_hash=_token_hash(access_token),
        expires_at=now + timedelta(hours=settings.visitor_session_ttl_hours),
        last_activity_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, access_token


def purge_expired_visitor_sessions() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            delete(VisitorSession)
            .where(VisitorSession.expires_at <= now)
            .execution_options(synchronize_session=False)
        )
        db.commit()


def _get_authorized_session(
    db: Session,
    session_id: uuid.UUID,
    access_token: str,
    *,
    lock: bool = False,
) -> VisitorSession:
    statement = select(VisitorSession).where(VisitorSession.id == session_id)
    if lock:
        statement = statement.with_for_update()
    session = db.scalar(statement)
    if session is None:
        raise VisitorSessionNotFound

    # Authenticate first so an unauthenticated caller cannot trigger deletion.
    if not secrets.compare_digest(session.token_hash, _token_hash(access_token)):
        raise InvalidVisitorToken
    _ensure_not_expired(db, session)
    return session


def _ensure_not_expired(db: Session, session: VisitorSession) -> None:
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise VisitorSessionExpired


def _trim_memory(db: Session, session_id: uuid.UUID) -> None:
    older_messages = (
        select(VisitorMessage.id)
        .where(VisitorMessage.session_id == session_id)
        .order_by(VisitorMessage.created_at.desc(), VisitorMessage.id.desc())
        .offset(settings.visitor_memory_max_messages)
    )
    db.execute(delete(VisitorMessage).where(VisitorMessage.id.in_(older_messages)))


def get_recent_messages(
    db: Session, session_id: uuid.UUID, access_token: str
) -> list[VisitorMessage]:
    _get_authorized_session(db, session_id, access_token)
    statement = (
        select(VisitorMessage)
        .where(VisitorMessage.session_id == session_id)
        .order_by(VisitorMessage.created_at.desc(), VisitorMessage.id.desc())
        .limit(settings.visitor_memory_max_messages)
    )
    return list(reversed(db.scalars(statement).all()))


def add_user_message(
    db: Session,
    session_id: uuid.UUID,
    access_token: str,
    content: str,
) -> tuple[VisitorMessage, int]:
    session = _get_authorized_session(db, session_id, access_token, lock=True)
    if session.turn_count >= settings.visitor_session_max_messages:
        raise VisitorMessageLimitReached

    now = datetime.now(timezone.utc)
    message = VisitorMessage(
        session_id=session.id,
        role="user",
        content=content,
    )
    session.turn_count += 1
    session.last_activity_at = now
    db.add(message)
    db.flush()
    _trim_memory(db, session.id)
    db.commit()
    db.refresh(message)
    return message, settings.visitor_session_max_messages - session.turn_count


def add_assistant_message(
    db: Session, session_id: uuid.UUID, content: str
) -> VisitorMessage:
    """Store an assistant reply in the temporary memory.

    Server-side hook for the future dialogue agent: it is deliberately not
    exposed over HTTP so clients cannot forge assistant turns. Assistant
    replies do not count towards the visitor message limit.
    """
    statement = (
        select(VisitorSession)
        .where(VisitorSession.id == session_id)
        .with_for_update()
    )
    session = db.scalar(statement)
    if session is None:
        raise VisitorSessionNotFound
    _ensure_not_expired(db, session)

    message = VisitorMessage(session_id=session.id, role="assistant", content=content)
    session.last_activity_at = datetime.now(timezone.utc)
    db.add(message)
    db.flush()
    _trim_memory(db, session.id)
    db.commit()
    db.refresh(message)
    return message


def delete_visitor_session(
    db: Session, session_id: uuid.UUID, access_token: str
) -> None:
    session = _get_authorized_session(db, session_id, access_token)
    db.delete(session)
    db.commit()
