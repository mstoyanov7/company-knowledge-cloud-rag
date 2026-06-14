from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from shared_schemas import SystemRuntimeSettings, get_settings

from sync_worker.onenote import build_onenote_sync_service
from sync_worker.ops.daily_schedule import load_timezone, next_run_at
from sync_worker.persistence import PostgresOpsStore


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the OneNote incremental sync.")
    parser.add_argument(
        "--run-loop",
        action="store_true",
        help="Run incremental polling continuously using the configured interval.",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    service = build_onenote_sync_service(settings)
    store = PostgresOpsStore(settings)
    logger = logging.getLogger("sync_worker.jobs.onenote_incremental")
    if not args.run_loop:
        report = service.incremental()
        logger.info(
            "event=onenote_incremental_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s",
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
        )
        return

    while True:
        runtime = _runtime_settings(store, settings, logger)
        if runtime.onenote_sync_paused:
            logger.info("event=onenote_incremental_paused")
            time.sleep(max(5, min(settings.worker_poll_interval_seconds, 30)))
            continue

        # Wait for the next daily scheduled time before syncing. If the schedule
        # changes or sync is paused while waiting, bail out and re-evaluate.
        if not _wait_until_daily_time(store, settings, logger, runtime.onenote_sync_daily_time):
            continue

        report = service.incremental()
        logger.info(
            "event=onenote_incremental_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s",
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
        )


def _runtime_settings(
    store: PostgresOpsStore,
    settings,
    logger: logging.Logger,
) -> SystemRuntimeSettings:
    try:
        return store.get_system_runtime_settings()
    except Exception:
        logger.exception("event=onenote_runtime_settings_unavailable action=using_env_defaults")
        return SystemRuntimeSettings(
            llm_model=settings.default_model_name,
            onenote_sync_interval_seconds=settings.onenote_sync_interval_seconds,
            onenote_sync_daily_time=settings.onenote_sync_daily_time,
            onenote_sync_paused=False,
        )


def _wait_until_daily_time(
    store: PostgresOpsStore,
    settings,
    logger: logging.Logger,
    daily_time: str,
) -> bool:
    """Sleep until the next daily scheduled time, in onenote_sync_timezone.

    Returns ``True`` when the scheduled time is reached, or ``False`` if sync is
    paused or the scheduled time is changed while waiting (so the caller loops
    and recomputes). Settings are re-checked periodically so changes from the
    admin panel take effect without restarting the worker.
    """
    tz_name = settings.onenote_sync_timezone
    target = next_run_at(daily_time, tz_name)
    logger.info(
        "event=onenote_incremental_scheduled next_run=%s timezone=%s daily_time=%s",
        target.isoformat(),
        tz_name,
        daily_time,
    )
    check_interval = max(5, min(settings.worker_poll_interval_seconds, 30))
    while True:
        now = datetime.now(load_timezone(tz_name))
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, check_interval))
        try:
            runtime = store.get_system_runtime_settings()
        except Exception:
            continue
        if runtime.onenote_sync_paused:
            return False
        if runtime.onenote_sync_daily_time != daily_time:
            return False


if __name__ == "__main__":
    run()
