from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.visitor import (
    VisitorMessageAdded,
    VisitorMessageCreate,
    VisitorMessageResponse,
    VisitorSessionCreated,
)
from app.services.visitor_sessions import (
    InvalidVisitorToken,
    VisitorMessageLimitReached,
    VisitorSessionExpired,
    VisitorSessionNotFound,
    add_user_message,
    create_visitor_session,
    delete_visitor_session,
    get_recent_messages,
)

router = APIRouter(prefix="/api/visitor-sessions", tags=["visitor sessions"])
bearer_scheme = HTTPBearer(auto_error=False)


def _access_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A visitor session token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def _raise_session_error(error: Exception) -> NoReturn:
    if isinstance(error, VisitorSessionNotFound):
        raise HTTPException(status_code=404, detail="Visitor session not found.") from error
    if isinstance(error, VisitorSessionExpired):
        raise HTTPException(status_code=410, detail="Visitor session has expired.") from error
    if isinstance(error, InvalidVisitorToken):
        raise HTTPException(
            status_code=401,
            detail="Invalid visitor session token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    if isinstance(error, VisitorMessageLimitReached):
        raise HTTPException(
            status_code=429,
            detail="Visitor session message limit reached.",
        ) from error
    raise error


@router.post("", response_model=VisitorSessionCreated, status_code=201)
def create_session(db: Annotated[Session, Depends(get_db)]) -> VisitorSessionCreated:
    session, access_token = create_visitor_session(db)
    return VisitorSessionCreated(
        session_id=session.id,
        access_token=access_token,
        expires_at=session.expires_at,
        message_limit=settings.visitor_session_max_messages,
        memory_limit=settings.visitor_memory_max_messages,
        messages_remaining=settings.visitor_session_max_messages,
    )


@router.get(
    "/{session_id}/messages",
    response_model=list[VisitorMessageResponse],
)
def list_messages(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(_access_token)],
) -> list[VisitorMessageResponse]:
    try:
        return get_recent_messages(db, session_id, token)
    except (VisitorSessionNotFound, VisitorSessionExpired, InvalidVisitorToken) as exc:
        _raise_session_error(exc)


@router.post(
    "/{session_id}/messages",
    response_model=VisitorMessageAdded,
    status_code=201,
)
def append_message(
    session_id: UUID,
    payload: VisitorMessageCreate,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(_access_token)],
) -> VisitorMessageAdded:
    try:
        message, remaining = add_user_message(
            db, session_id, token, payload.content
        )
    except (
        VisitorSessionNotFound,
        VisitorSessionExpired,
        InvalidVisitorToken,
        VisitorMessageLimitReached,
    ) as exc:
        _raise_session_error(exc)
    return VisitorMessageAdded(
        message=VisitorMessageResponse.model_validate(message),
        messages_remaining=remaining,
    )


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(_access_token)],
) -> Response:
    try:
        delete_visitor_session(db, session_id, token)
    except (VisitorSessionNotFound, VisitorSessionExpired, InvalidVisitorToken) as exc:
        _raise_session_error(exc)
    return Response(status_code=204)
