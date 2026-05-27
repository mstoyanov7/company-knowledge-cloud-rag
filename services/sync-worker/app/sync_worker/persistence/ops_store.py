from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
from shared_schemas import (
    AppSettings,
    EvaluationReport,
    OpsJobRecord,
    OpsJobStatus,
    SecurityAuditEvent,
)


class PostgresOpsStore:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def ensure_schema(self) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(hashtext('cloud_rag_ops_schema'))")
                try:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ops_jobs (
                            job_id TEXT PRIMARY KEY,
                            job_type TEXT NOT NULL,
                            dedupe_key TEXT NOT NULL UNIQUE,
                            payload_json TEXT NOT NULL,
                            status TEXT NOT NULL,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            max_attempts INTEGER NOT NULL DEFAULT 5,
                            available_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            locked_at_utc TIMESTAMPTZ,
                            locked_by TEXT,
                            last_error TEXT,
                            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            completed_at_utc TIMESTAMPTZ
                        );

                        CREATE INDEX IF NOT EXISTS idx_ops_jobs_status_available
                            ON ops_jobs(status, available_at_utc);
                        CREATE INDEX IF NOT EXISTS idx_ops_jobs_type
                            ON ops_jobs(job_type);

                        CREATE TABLE IF NOT EXISTS dead_letters (
                            dead_letter_id TEXT PRIMARY KEY,
                            job_id TEXT NOT NULL,
                            job_type TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            error TEXT NOT NULL,
                            attempts INTEGER NOT NULL,
                            failed_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_dead_letters_job_id
                            ON dead_letters(job_id);

                        CREATE TABLE IF NOT EXISTS ops_metrics (
                            metric_id TEXT PRIMARY KEY,
                            metric_name TEXT NOT NULL,
                            labels_json TEXT NOT NULL,
                            value DOUBLE PRECISION NOT NULL,
                            recorded_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_ops_metrics_name_time
                            ON ops_metrics(metric_name, recorded_at_utc);

                        CREATE TABLE IF NOT EXISTS security_audit_events (
                            event_id TEXT PRIMARY KEY,
                            event_type TEXT NOT NULL,
                            outcome TEXT NOT NULL,
                            actor_user_id TEXT,
                            tenant_id TEXT,
                            resource_type TEXT,
                            resource_id TEXT,
                            metadata_json TEXT NOT NULL,
                            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_security_audit_actor_time
                            ON security_audit_events(actor_user_id, created_at_utc);
                        CREATE INDEX IF NOT EXISTS idx_security_audit_type_time
                            ON security_audit_events(event_type, created_at_utc);

                        CREATE TABLE IF NOT EXISTS evaluation_runs (
                            run_id TEXT PRIMARY KEY,
                            dataset_path TEXT NOT NULL,
                            summary_json TEXT NOT NULL,
                            report_json TEXT NOT NULL,
                            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )
                finally:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext('cloud_rag_ops_schema'))")
            connection.commit()

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        dedupe_key: str | None = None,
        max_attempts: int | None = None,
        available_at_utc: datetime | None = None,
    ) -> tuple[OpsJobRecord, bool]:
        self.ensure_schema()
        payload = payload or {}
        now = datetime.now(UTC)
        job_id = str(uuid4())
        resolved_dedupe_key = dedupe_key or f"{job_type}:{job_id}"
        resolved_available_at = available_at_utc or now
        resolved_max_attempts = max_attempts or self.settings.ops_job_max_attempts

        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ops_jobs (
                        job_id, job_type, dedupe_key, payload_json, status, attempts, max_attempts,
                        available_at_utc, created_at_utc, updated_at_utc
                    ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s)
                    ON CONFLICT (dedupe_key) DO NOTHING
                    RETURNING job_id, job_type, dedupe_key, payload_json, status, attempts, max_attempts,
                              available_at_utc, locked_at_utc, locked_by, last_error, created_at_utc,
                              updated_at_utc, completed_at_utc
                    """,
                    (
                        job_id,
                        job_type,
                        resolved_dedupe_key,
                        _json_dump(payload),
                        OpsJobStatus.pending.value,
                        resolved_max_attempts,
                        resolved_available_at,
                        now,
                        now,
                    ),
                )
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        """
                        SELECT job_id, job_type, dedupe_key, payload_json, status, attempts, max_attempts,
                               available_at_utc, locked_at_utc, locked_by, last_error, created_at_utc,
                               updated_at_utc, completed_at_utc
                        FROM ops_jobs
                        WHERE dedupe_key = %s
                        """,
                        (resolved_dedupe_key,),
                    )
                    row = cursor.fetchone()
            connection.commit()

        if row is None:
            raise RuntimeError(f"Failed to enqueue or locate ops job for dedupe_key={resolved_dedupe_key}")
        return _job_from_row(row), created

    def claim_next_job(self, worker_id: str) -> OpsJobRecord | None:
        self.ensure_schema()
        now = datetime.now(UTC)
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT job_id
                        FROM ops_jobs
                        WHERE status IN (%s, %s)
                          AND available_at_utc <= NOW()
                        ORDER BY available_at_utc ASC, created_at_utc ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE ops_jobs
                    SET status = %s,
                        attempts = attempts + 1,
                        locked_at_utc = %s,
                        locked_by = %s,
                        updated_at_utc = %s
                    FROM candidate
                    WHERE ops_jobs.job_id = candidate.job_id
                    RETURNING ops_jobs.job_id, ops_jobs.job_type, ops_jobs.dedupe_key, ops_jobs.payload_json,
                              ops_jobs.status, ops_jobs.attempts, ops_jobs.max_attempts,
                              ops_jobs.available_at_utc, ops_jobs.locked_at_utc, ops_jobs.locked_by,
                              ops_jobs.last_error, ops_jobs.created_at_utc, ops_jobs.updated_at_utc,
                              ops_jobs.completed_at_utc
                    """,
                    (
                        OpsJobStatus.pending.value,
                        OpsJobStatus.failed.value,
                        OpsJobStatus.running.value,
                        now,
                        worker_id,
                        now,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return _job_from_row(row) if row else None

    def mark_job_succeeded(self, job_id: str) -> None:
        now = datetime.now(UTC)
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ops_jobs
                    SET status = %s,
                        locked_at_utc = NULL,
                        locked_by = NULL,
                        last_error = NULL,
                        completed_at_utc = %s,
                        updated_at_utc = %s
                    WHERE job_id = %s
                    """,
                    (OpsJobStatus.succeeded.value, now, now, job_id),
                )
            connection.commit()

    def mark_job_failed(self, job: OpsJobRecord, error: str) -> None:
        now = datetime.now(UTC)
        if job.attempts >= job.max_attempts:
            with psycopg.connect(self.settings.postgres_dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ops_jobs
                        SET status = %s,
                            locked_at_utc = NULL,
                            locked_by = NULL,
                            last_error = %s,
                            completed_at_utc = %s,
                            updated_at_utc = %s
                        WHERE job_id = %s
                        """,
                        (OpsJobStatus.dead_letter.value, error, now, now, job.job_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO dead_letters (
                            dead_letter_id, job_id, job_type, payload_json, error, attempts, failed_at_utc
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (dead_letter_id) DO NOTHING
                        """,
                        (
                            str(uuid4()),
                            job.job_id,
                            job.job_type,
                            _json_dump(job.payload),
                            error,
                            job.attempts,
                            now,
                        ),
                    )
                connection.commit()
            return

        delay = compute_backoff_seconds(
            job.attempts,
            self.settings.ops_job_base_backoff_seconds,
            self.settings.ops_job_max_backoff_seconds,
        )
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ops_jobs
                    SET status = %s,
                        available_at_utc = %s,
                        locked_at_utc = NULL,
                        locked_by = NULL,
                        last_error = %s,
                        updated_at_utc = %s
                    WHERE job_id = %s
                    """,
                    (
                        OpsJobStatus.failed.value,
                        now + timedelta(seconds=delay),
                        error,
                        now,
                        job.job_id,
                    ),
                )
            connection.commit()

    def record_metric(self, metric_name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        self.ensure_schema()
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ops_metrics (metric_id, metric_name, labels_json, value, recorded_at_utc)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (str(uuid4()), metric_name, _json_dump(labels or {}), value, datetime.now(UTC)),
                )
            connection.commit()

    def record_security_audit_event(self, event: SecurityAuditEvent) -> None:
        if not self.settings.security_audit_log_to_db:
            return
        self.ensure_schema()
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO security_audit_events (
                        event_id, event_type, outcome, actor_user_id, tenant_id, resource_type,
                        resource_id, metadata_json, created_at_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid4()),
                        event.event_type,
                        event.outcome,
                        event.actor_user_id,
                        event.tenant_id,
                        event.resource_type,
                        event.resource_id,
                        _json_dump(event.metadata),
                        event.created_at_utc,
                    ),
                )
            connection.commit()

    def record_evaluation_report(self, report: EvaluationReport) -> None:
        self.ensure_schema()
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO evaluation_runs (run_id, dataset_path, summary_json, report_json, created_at_utc)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        dataset_path = EXCLUDED.dataset_path,
                        summary_json = EXCLUDED.summary_json,
                        report_json = EXCLUDED.report_json,
                        created_at_utc = EXCLUDED.created_at_utc
                    """,
                    (
                        report.summary.run_id,
                        report.summary.dataset_path,
                        report.summary.model_dump_json(),
                        report.model_dump_json(),
                        report.summary.generated_at_utc,
                    ),
                )
            connection.commit()


def compute_backoff_seconds(attempt: int, base_seconds: int, max_seconds: int) -> int:
    if attempt <= 1:
        return min(base_seconds, max_seconds)
    return min(base_seconds * (2 ** (attempt - 1)), max_seconds)


def _job_from_row(row) -> OpsJobRecord:
    return OpsJobRecord(
        job_id=row[0],
        job_type=row[1],
        dedupe_key=row[2],
        payload=json.loads(row[3]),
        status=row[4],
        attempts=row[5],
        max_attempts=row[6],
        available_at_utc=row[7],
        locked_at_utc=row[8],
        locked_by=row[9],
        last_error=row[10],
        created_at_utc=row[11],
        updated_at_utc=row[12],
        completed_at_utc=row[13],
    )


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, default=_json_default, sort_keys=True)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)
