from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from uuid import uuid4

from shared_schemas import AppSettings, OpsJobRecord, OpsJobType

from sync_worker.observability import configure_observability
from sync_worker.onenote import build_onenote_sync_service
from sync_worker.ops.scheduler import OpsScheduler
from sync_worker.persistence import PostgresOpsStore
from sync_worker.topics import refresh_app_topics_from_sources

try:
    from opentelemetry import metrics, trace
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    metrics = None
    trace = None


class OpsJobRunner:
    def __init__(self, settings: AppSettings, *, store: PostgresOpsStore | None = None) -> None:
        configure_observability(settings, default_service_name="sync-worker")
        self.settings = settings
        self.store = store or PostgresOpsStore(settings)
        self.worker_id = f"ops-worker-{uuid4()}"
        self.logger = logging.getLogger("sync_worker.ops.job_runner")
        self.tracer = trace.get_tracer("sync_worker.ops") if trace else None
        self.job_latency_ms = (
            metrics.get_meter("sync_worker.ops").create_histogram("sync_worker_job_latency_ms") if metrics else None
        )

    def process_once(self, *, enqueue_periodic: bool = True) -> bool:
        if enqueue_periodic:
            enqueued = OpsScheduler(self.settings, self.store).enqueue_periodic_jobs()
            if enqueued:
                self.logger.info("event=ops_periodic_jobs_enqueued count=%s", enqueued)

        job = self.store.claim_next_job(self.worker_id)
        if job is None:
            return False

        started = time.perf_counter()
        span = self.tracer.start_as_current_span(f"ops.{job.job_type}") if self.tracer else nullcontext()
        with span:
            try:
                self.logger.info(
                    "event=ops_job_started job_id=%s job_type=%s attempt=%s",
                    job.job_id,
                    job.job_type,
                    job.attempts,
                )
                self._execute(job)
                self.store.mark_job_succeeded(job.job_id)
                duration_ms = int((time.perf_counter() - started) * 1000)
                if self.job_latency_ms:
                    self.job_latency_ms.record(duration_ms, {"job_type": job.job_type, "status": "succeeded"})
                self.store.record_metric("sync_worker_job_latency_ms", duration_ms, {"job_type": job.job_type})
                self.logger.info(
                    "event=ops_job_succeeded job_id=%s job_type=%s duration_ms=%s",
                    job.job_id,
                    job.job_type,
                    duration_ms,
                )
                return True
            except Exception as error:
                duration_ms = int((time.perf_counter() - started) * 1000)
                if self.job_latency_ms:
                    self.job_latency_ms.record(duration_ms, {"job_type": job.job_type, "status": "failed"})
                self.store.mark_job_failed(job, str(error))
                self.logger.exception(
                    "event=ops_job_failed job_id=%s job_type=%s attempt=%s",
                    job.job_id,
                    job.job_type,
                    job.attempts,
                )
                return True

    def run_loop(self) -> None:
        while True:
            processed_any = False
            for _ in range(max(1, self.settings.ops_worker_batch_size)):
                processed = self.process_once(enqueue_periodic=not processed_any)
                processed_any = processed_any or processed
                if not processed:
                    break
            time.sleep(self.settings.worker_poll_interval_seconds)

    def _execute(self, job: OpsJobRecord) -> None:
        if job.job_type == OpsJobType.onenote_reconciliation.value:
            runtime = self.store.get_system_runtime_settings()
            if runtime.onenote_sync_paused and job.payload.get("trigger") != "admin":
                self.logger.info("event=ops_job_skipped reason=onenote_sync_paused job_id=%s", job.job_id)
                return
            build_onenote_sync_service(self.settings).reconciliation()
            refresh_app_topics_from_sources(self.settings)
            return

        raise ValueError(f"Unsupported ops job_type={job.job_type}")
