from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    idle = "idle"
    planned = "planned"
    running = "running"
    failed = "failed"
    completed = "completed"


class SyncJob(BaseModel):
    job_name: str
    connector_name: str
    schedule_interval_seconds: int
    status: JobStatus = JobStatus.planned
    scope_summary: str
    last_run_utc: datetime | None = None
    next_run_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SyncMode(StrEnum):
    bootstrap = "bootstrap"
    incremental = "incremental"


class SharePointCheckpoint(BaseModel):
    scope_key: str
    sync_mode: SyncMode
    site_id: str | None = None
    drive_id: str | None = None
    cursor_url: str | None = None
    delta_link: str | None = None
    page_count: int = 0
    item_count: int = 0
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OneNoteCheckpoint(BaseModel):
    scope_key: str
    sync_mode: SyncMode
    site_id: str | None = None
    notebook_scope: str | None = None
    last_modified_cursor_utc: datetime | None = None
    page_count: int = 0
    item_count: int = 0
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SyncReport(BaseModel):
    job_name: str
    scope_key: str
    pages_processed: int = 0
    items_seen: int = 0
    items_changed: int = 0
    items_skipped: int = 0
    items_deleted: int = 0
    chunks_written: int = 0
    checkpoint: SharePointCheckpoint | OneNoteCheckpoint | None = None
