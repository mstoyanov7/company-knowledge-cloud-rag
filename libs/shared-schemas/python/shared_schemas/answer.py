from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from shared_schemas.documents import DownloadLink, RetrievalMetadata, UserContext


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
    last_edited_by: str | None = None
    client_url: str | None = None
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
    # Coarse outcome of the answer pipeline, for evaluation/guardrail accounting:
    # "answered" (model answer kept), "extractive" (model answer replaced by a
    # source extract by the 4.3.3 guard), "hedged", "clarify", or "refusal".
    answer_kind: str | None = None


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AnswerRequest(BaseModel):
    topic_id: str | None = Field(default=None, min_length=1, max_length=120)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=120)
    answer_style: str | None = Field(default=None, max_length=120)
    answer_depth: Literal["concise", "normal", "detailed"] = "detailed"
    question: str = Field(min_length=3, max_length=1000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=40)
    user_context: UserContext = Field(default_factory=UserContext)
    source_filters: list[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=10)
    provider: str | None = None
    # When set (after the user answers a clarifying question), retrieval and
    # ranking are restricted to these OneNote pages so the answer comes from the
    # page the user chose.
    focus_source_item_ids: list[str] = Field(default_factory=list, max_length=10)


class ClarificationOption(BaseModel):
    """One candidate page the user can pick when a question is ambiguous."""

    source_item_id: str
    title: str
    section_path: str | None = None
    hint: str = ""


class Clarification(BaseModel):
    """A quiz-style follow-up asking the user which page they mean."""

    prompt: str
    options: list[ClarificationOption]
    original_question: str


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    downloads: list[DownloadLink] = Field(default_factory=list)
    retrieval_meta: RetrievalMetadata
    metadata: AnswerMetadata
    suggested_questions: list[str] = Field(default_factory=list)
    # Present only when the backend needs the user to disambiguate between
    # several equally-plausible pages before it can answer.
    clarification: Clarification | None = None
