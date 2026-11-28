from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings


class VisitorSessionCreated(BaseModel):
    session_id: UUID
    access_token: str
    expires_at: datetime
    message_limit: int
    memory_limit: int
    messages_remaining: int


class VisitorMessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=settings.visitor_message_max_length,
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank.")
        return value


class VisitorMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class VisitorMessageAdded(BaseModel):
    message: VisitorMessageResponse
    messages_remaining: int
