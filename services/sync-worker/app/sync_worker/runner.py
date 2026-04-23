import logging
import time
from datetime import UTC, datetime

from graph_connectors import OneNoteConnector, SharePointConnector
from shared_schemas import AppSettings, JobStatus, SyncJob


class WorkerRunner:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger("sync_worker.runner")
        self.sharepoint = SharePointConnector(settings)
        self.onenote = OneNoteConnector(settings)

    def plan_jobs(self) -> list[SyncJob]:
        now = datetime.now(UTC)
        return [
            SyncJob(
                job_name="sharepoint_bootstrap",
                connector_name=self.sharepoint.connector_name,
                schedule_interval_seconds=self.sharepoint.sync_interval_seconds(),
                scope_summary=self.sharepoint.describe_scope(),
                status=JobStatus.planned,
                next_run_utc=now,
            ),
            SyncJob(
                job_name="sharepoint_incremental",
                connector_name=self.sharepoint.connector_name,
                schedule_interval_seconds=self.sharepoint.sync_interval_seconds(),
                scope_summary=self.sharepoint.describe_scope(),
                status=JobStatus.planned,
                next_run_utc=now,
            ),
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
                job_name="nightly_reconciliation_job",
                connector_name="scheduler",
                schedule_interval_seconds=86400,
                scope_summary="Full reconciliation placeholder for missed or failed changes.",
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
