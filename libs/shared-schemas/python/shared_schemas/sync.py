from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    idle = "idle"
    planned = "planned"
    running = "running"
    failed = "failed"


class SyncJob(BaseModel):
    job_name: str
    connector_name: str
    schedule_interval_seconds: int
    status: JobStatus = JobStatus.planned
    scope_summary: str
    last_run_utc: datetime | None = None
    next_run_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
