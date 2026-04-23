from __future__ import annotations

import argparse
import logging
import time

from shared_schemas import get_settings

from sync_worker.sharepoint import build_sharepoint_sync_service


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the SharePoint incremental sync.")
    parser.add_argument(
        "--run-loop",
        action="store_true",
        help="Run incremental sync continuously using the configured interval.",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    service = build_sharepoint_sync_service(settings)
    logger = logging.getLogger("sync_worker.jobs.sharepoint_incremental")
    if not args.run_loop:
        report = service.incremental()
        logger.info(
            "event=sharepoint_incremental_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s",
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
        )
        return

    while True:
        report = service.incremental()
        logger.info(
            "event=sharepoint_incremental_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s",
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
        )
        time.sleep(settings.sharepoint_sync_interval_seconds)


if __name__ == "__main__":
    run()
