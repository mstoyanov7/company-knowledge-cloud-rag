from __future__ import annotations

import time

from shared_schemas import AppSettings, OpsJobType

from sync_worker.persistence import PostgresOpsStore


class OpsScheduler:
    def __init__(self, settings: AppSettings, store: PostgresOpsStore | None = None) -> None:
        self.settings = settings
        self.store = store or PostgresOpsStore(settings)

    def enqueue_periodic_jobs(self) -> int:
        try:
            if self.store.get_system_runtime_settings().onenote_sync_paused:
                return 0
        except Exception:
            pass

        enqueued = 0
        for job_type, interval in [
            (OpsJobType.onenote_reconciliation.value, self.settings.onenote_reconciliation_interval_seconds),
        ]:
            if interval <= 0:
                continue
            slot = int(time.time() // interval)
            _job, created = self.store.enqueue_job(
                job_type,
                {"scheduled_slot": slot, "interval_seconds": interval},
                dedupe_key=f"{job_type}:{slot}",
                max_attempts=self.settings.ops_job_max_attempts,
            )
            if created:
                enqueued += 1
        return enqueued
