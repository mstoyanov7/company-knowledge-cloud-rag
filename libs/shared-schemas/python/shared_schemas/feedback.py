from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    response_id: str = Field(min_length=1, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=120)
    rating: Literal["up", "down"] | None = None
    flag_gap: bool = False
    comment: str | None = Field(default=None, max_length=2000)
    question: str = Field(min_length=1, max_length=1000)
    topic_id: str | None = Field(default=None, max_length=120)


class FeedbackResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"fb-{uuid4().hex[:12]}")
    response_id: str
    conversation_id: str | None = None
    rating: Literal["up", "down"] | None = None
    flag_gap: bool = False
    comment: str | None = None
    question: str
    topic_id: str | None = None
    user_id: str
    tenant_id: str
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

