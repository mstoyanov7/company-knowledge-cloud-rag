from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from shared_schemas.documents import UserContext


class EvaluationCase(BaseModel):
    case_id: str
    question: str
    expected_source_item_ids: list[str] = Field(default_factory=list)
    expected_answer_terms: list[str] = Field(default_factory=list)
    user_context: UserContext = Field(default_factory=UserContext)
    source_filters: list[str] = Field(default_factory=list)
    top_k: int = 3


class EvaluationCaseResult(BaseModel):
    case_id: str
    question: str
    answer: str
    retrieved_source_item_ids: list[str]
    expected_source_item_ids: list[str]
    citation_correctness: float
    document_recall: float
    retrieval_hit: bool
    groundedness: float
    latency_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(BaseModel):
    run_id: str
    dataset_path: str
    case_count: int
    retrieval_hit_rate: float
    mean_document_recall: float
    mean_citation_correctness: float
    mean_groundedness: float
    mean_latency_ms: float
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationReport(BaseModel):
    summary: EvaluationSummary
    cases: list[EvaluationCaseResult]
