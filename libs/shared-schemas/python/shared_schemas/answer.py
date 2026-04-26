from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from shared_schemas.documents import RetrievalMetadata, UserContext


class Citation(BaseModel):
    index: int
    chunk_id: str
    source_item_id: str
    chunk_index: int
    title: str
    source_system: str
    source_container: str
    source_url: str
    section_path: str | None = None
    snippet: str
    last_modified_utc: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnswerMetadata(BaseModel):
    response_id: str = Field(default_factory=lambda: f"resp-{uuid4().hex[:12]}")
    provider: str
    model: str
    retrieval_strategy: str
    retrieved_chunk_count: int
    source_systems: list[str]
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int
    retrieval_latency_ms: int = 0
    completion_latency_ms: int = 0
    freshness_delay_ms: int | None = None
    citation_count: int = 0


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    user_context: UserContext = Field(default_factory=UserContext)
    source_filters: list[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=10)
    provider: str | None = None


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_meta: RetrievalMetadata
    metadata: AnswerMetadata
