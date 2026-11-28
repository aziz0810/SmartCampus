"""Pydantic schemas for authentication endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # Optional: link the ongoing visitor session on registration
    visitor_session_id: uuid.UUID | None = None


class ClaimSessionRequest(BaseModel):
    visitor_session_id: uuid.UUID


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str          # role code, e.g. "candidat" or "responsable"
    is_active: bool
    last_login_at: datetime | None


# Fix forward ref
TokenResponse.model_rebuild()


class ClaimSessionResponse(BaseModel):
    session_id: uuid.UUID
    claimed: bool
