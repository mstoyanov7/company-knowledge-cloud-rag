import logging
import time
from datetime import UTC, datetime

from graph_connectors import OneNoteConnector
from shared_schemas import AppSettings, JobStatus, SyncJob


class WorkerRunner:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger("sync_worker.runner")
        self.onenote = OneNoteConnector(settings)

    def plan_jobs(self) -> list[SyncJob]:
        now = datetime.now(UTC)
        return [
            SyncJob(
                job_name="onenote_bootstrap",
                connector_name=self.onenote.connector_name,
                schedule_interval_seconds=self.onenote.sync_interval_seconds(),
                scope_summary=self.onenote.describe_scope(),
                status=JobStatus.planned,
                next_run_utc=now,
            ),
            SyncJob(
                job_name="onenote_incremental",
                connector_name=self.onenote.connector_name,
                schedule_interval_seconds=self.onenote.sync_interval_seconds(),
                scope_summary=self.onenote.describe_scope(),
                status=JobStatus.planned,
                next_run_utc=now,
            ),
            SyncJob(
                job_name="ops_worker",
                connector_name="operations",
                schedule_interval_seconds=self.settings.worker_poll_interval_seconds,
                scope_summary="Durable PostgreSQL-backed queue for retries, dead letters, and OneNote reconciliation.",
                status=JobStatus.planned,
                next_run_utc=now,
            ),
            SyncJob(
                job_name="onenote_reconciliation",
                connector_name=self.onenote.connector_name,
                schedule_interval_seconds=self.settings.onenote_reconciliation_interval_seconds,
                scope_summary="Scheduled OneNote polling and inventory reconciliation.",
                status=JobStatus.planned,
                next_run_utc=now,
            ),
        ]

    def run_once(self) -> list[SyncJob]:
        jobs = self.plan_jobs()
        for job in jobs:
            self.logger.info(
                "planned job=%s connector=%s interval=%ss scope=%s",
                job.job_name,
                job.connector_name,
                job.schedule_interval_seconds,
                job.scope_summary,
            )
        return jobs

    def run_loop(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.settings.worker_poll_interval_seconds)
