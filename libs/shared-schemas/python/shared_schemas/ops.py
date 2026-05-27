from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OpsJobStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"


class OpsJobType(StrEnum):
    onenote_reconciliation = "onenote_reconciliation"


class OpsJobRecord(BaseModel):
    job_id: str
    job_type: str
    dedupe_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: OpsJobStatus = OpsJobStatus.pending
    attempts: int = 0
    max_attempts: int = 5
    available_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    locked_at_utc: datetime | None = None
    locked_by: str | None = None
    last_error: str | None = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at_utc: datetime | None = None


class DeadLetterRecord(BaseModel):
    dead_letter_id: str
    job_id: str
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str
    attempts: int
    failed_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
