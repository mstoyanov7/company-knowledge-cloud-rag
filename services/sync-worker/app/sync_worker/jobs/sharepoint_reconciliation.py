from __future__ import annotations

import logging

from shared_schemas import get_settings

from sync_worker.sharepoint import build_sharepoint_sync_service


def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    report = build_sharepoint_sync_service(settings).incremental()
    logging.getLogger("sync_worker.jobs.sharepoint_reconciliation").info(
        "event=sharepoint_reconciliation_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s",
        report.items_seen,
        report.items_changed,
        report.items_skipped,
        report.items_deleted,
        report.chunks_written,
    )


if __name__ == "__main__":
    run()
