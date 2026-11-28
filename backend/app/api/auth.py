"""Authentication API: login, register, /me, claim visitor session."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, OptionalUser, get_current_user
from app.db import get_db
from app.schemas.auth import (
    ClaimSessionRequest,
    ClaimSessionResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth import (
    EmailAlreadyExists,
    InactiveUser,
    RoleNotFound,
    UserNotFound,
    VisitorSessionAlreadyClaimed,
    VisitorSessionNotFound,
    WrongPassword,
    claim_visitor_session,
    login,
    register_candidate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.code,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login_endpoint(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        user, token = login(db, payload.email, payload.password)
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect.")
    except WrongPassword:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect.")
    except InactiveUser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé.")
    return TokenResponse(access_token=token, user=_user_out(user))


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_endpoint(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        user, token = register_candidate(
            db,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            visitor_session_id=payload.visitor_session_id,
        )
    except EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte existe déjà avec cet email.",
        )
    except RoleNotFound as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except VisitorSessionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session visiteur introuvable.",
        )
    except VisitorSessionAlreadyClaimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette session visiteur est déjà associée à un compte.",
        )
    return TokenResponse(access_token=token, user=_user_out(user))


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
def me_endpoint(user: CurrentUser) -> UserOut:
    return _user_out(user)


# ---------------------------------------------------------------------------
# POST /api/auth/claim-session  (authenticated candidates only)
# ---------------------------------------------------------------------------

@router.post("/claim-session", response_model=ClaimSessionResponse)
def claim_session_endpoint(
    payload: ClaimSessionRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ClaimSessionResponse:
    """Associate an existing anonymous visitor session to the authenticated user."""
    if user.role.code != "candidat":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les candidats peuvent associer une session visiteur.",
        )
    try:
        session = claim_visitor_session(db, payload.visitor_session_id, user)
    except VisitorSessionNotFound:
        raise HTTPException(status_code=404, detail="Session visiteur introuvable.")
    except VisitorSessionAlreadyClaimed:
        raise HTTPException(status_code=409, detail="Session déjà associée à un compte.")
    return ClaimSessionResponse(session_id=session.id, claimed=True)
