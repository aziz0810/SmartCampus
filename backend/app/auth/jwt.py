"""JWT creation and verification for SmartCampus."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from jwt import DecodeError, ExpiredSignatureError

from app.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int, role_code: str, *, ttl_minutes: int | None = None) -> str:
    minutes = ttl_minutes if ttl_minutes is not None else settings.jwt_access_token_ttl_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {
        "sub": str(user_id),
        "role": role_code,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT. Raises:
      - jwt.ExpiredSignatureError  → token expired
      - jwt.DecodeError            → invalid token
    """
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
