from __future__ import annotations

import argparse
import logging

from shared_schemas import get_settings

from sync_worker.onenote import build_onenote_sync_service
from sync_worker.topics import refresh_app_topics_from_sources


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the OneNote bootstrap crawl.")
    args = parser.parse_args()
    _ = args

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    service = build_onenote_sync_service(settings)
    report = service.bootstrap()
    topic_count = refresh_app_topics_from_sources(settings)
    logging.getLogger("sync_worker.jobs.onenote_bootstrap").info(
        "event=onenote_bootstrap_report items_seen=%s changed=%s skipped=%s deleted=%s chunks=%s topics=%s",
        report.items_seen,
        report.items_changed,
        report.items_skipped,
        report.items_deleted,
        report.chunks_written,
        topic_count,
    )


if __name__ == "__main__":
    run()
