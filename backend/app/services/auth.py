"""Authentication service: login, register, session claim."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.models.identity import AppUser, Role
from app.models.visitor import VisitorSession


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class UserNotFound(Exception):
    pass


class WrongPassword(Exception):
    pass


class InactiveUser(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class RoleNotFound(Exception):
    pass


class VisitorSessionNotFound(Exception):
    pass


class VisitorSessionAlreadyClaimed(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANDIDATE_ROLE = "candidat"
RESPONSIBLE_ROLE = "responsable"


def _get_role(db: Session, code: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise RoleNotFound(f"Role '{code}' not found in database.")
    return role


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(db: Session, email: str, password: str) -> tuple[AppUser, str]:
    """Authenticate user. Returns (user, jwt_access_token)."""
    user = db.scalar(
        select(AppUser)
        .options(joinedload(AppUser.role))
        .where(AppUser.email == email)
    )
    if user is None:
        raise UserNotFound
    if not user.is_active:
        raise InactiveUser
    if not verify_password(password, user.password_hash):
        raise WrongPassword

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(user.id, user.role.code)
    return user, token


# ---------------------------------------------------------------------------
# Register (candidates self-register)
# ---------------------------------------------------------------------------

def register_candidate(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    visitor_session_id: uuid.UUID | None = None,
) -> tuple[AppUser, str]:
    """
    Create a new candidate account.
    If visitor_session_id is provided and valid, link it to the new user.
    Returns (user, jwt_access_token).
    """
    existing = db.scalar(select(AppUser).where(AppUser.email == email))
    if existing is not None:
        raise EmailAlreadyExists

    role = _get_role(db, CANDIDATE_ROLE)
    user = AppUser(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role_id=role.id,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()  # get user.id before commit

    # Optionally claim the visitor session
    if visitor_session_id is not None:
        _claim_session(db, visitor_session_id, user.id)

    db.commit()
    db.refresh(user)
    user.role  # eager-load after refresh

    token = create_access_token(user.id, role.code)
    return user, token


# ---------------------------------------------------------------------------
# Claim visitor session
# ---------------------------------------------------------------------------

def claim_visitor_session(
    db: Session,
    visitor_session_id: uuid.UUID,
    user: AppUser,
) -> VisitorSession:
    """
    Associate an existing anonymous visitor session to an authenticated user.
    Can be called after login if the user had a pending visitor session.
    """
    session = _claim_session(db, visitor_session_id, user.id)
    db.commit()
    return session


def _claim_session(
    db: Session,
    visitor_session_id: uuid.UUID,
    user_id: int,
) -> VisitorSession:
    session = db.get(VisitorSession, visitor_session_id)
    if session is None:
        raise VisitorSessionNotFound
    if session.claimed_by_user_id is not None:
        raise VisitorSessionAlreadyClaimed
    session.claimed_by_user_id = user_id
    return session
