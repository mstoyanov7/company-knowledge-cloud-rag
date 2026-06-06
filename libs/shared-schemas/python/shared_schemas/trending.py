from datetime import datetime

from pydantic import BaseModel, Field


class TrendingQuestion(BaseModel):
    question: str = Field(min_length=1)
    topic_id: str | None = None
    count: int = Field(ge=1)
    unique_users: int = Field(default=1, ge=1)
    last_asked_utc: datetime | None = None

