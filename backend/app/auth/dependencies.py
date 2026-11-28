"""FastAPI dependency injectors for authentication and authorisation."""
from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.db import get_db
from app.models.identity import AppUser

_bearer = HTTPBearer(auto_error=False)


def _get_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_user(
    token: Annotated[str, Depends(_get_token)],
    db: Annotated[Session, Depends(get_db)],
) -> AppUser:
    """Resolve the JWT to a live, active AppUser row."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.DecodeError):
        raise credentials_error

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = db.get(AppUser, int(user_id))
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def require_role(*roles: str):
    """Factory: returns a dependency that enforces one of the given role codes."""

    def _check(user: CurrentUser) -> AppUser:
        from app.models.identity import Role
        # role_code is embedded in the JWT; re-check against DB role
        if user.role.code not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return Depends(_check)


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> AppUser | None:
    """Like get_current_user but returns None instead of raising for unauthenticated requests."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user = db.get(AppUser, int(user_id))
        return user if (user and user.is_active) else None
    except (jwt.ExpiredSignatureError, jwt.DecodeError):
        return None


OptionalUser = Annotated[AppUser | None, Depends(get_optional_user)]
