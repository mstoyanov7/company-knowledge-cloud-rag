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


# 24-hour clock time, "HH:MM" (e.g. "02:00"). Used for the daily sync schedule.
_DAILY_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class SystemRuntimeSettings(BaseModel):
    llm_model: str
    # Retained for backward compatibility; the automatic sync is driven by
    # onenote_sync_daily_time, not by a seconds interval.
    onenote_sync_interval_seconds: int = Field(ge=60, le=86400)
    onenote_sync_daily_time: str = Field(default="02:00", pattern=_DAILY_TIME_PATTERN)
    onenote_sync_paused: bool = False
    updated_at_utc: datetime | None = None
    updated_by_user_id: str | None = None


class AdminSystemSettings(SystemRuntimeSettings):
    llm_provider: str
    available_llm_models: list[str] = Field(default_factory=list)
    # IANA timezone the daily sync time is interpreted in (display-only).
    onenote_sync_timezone: str = "UTC"
    last_sync_job: OpsJobRecord | None = None


class AdminSystemSettingsUpdate(BaseModel):
    llm_model: str | None = Field(default=None, min_length=1, max_length=160)
    onenote_sync_interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    onenote_sync_daily_time: str | None = Field(default=None, pattern=_DAILY_TIME_PATTERN)
    onenote_sync_paused: bool | None = None


class ForceSyncResponse(BaseModel):
    job: OpsJobRecord
    created: bool
    settings: AdminSystemSettings
