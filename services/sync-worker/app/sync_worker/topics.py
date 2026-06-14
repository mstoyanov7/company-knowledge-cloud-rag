from __future__ import annotations

import logging

from shared_schemas import AppSettings

from rag_api.adapters.source_metadata import PostgresSourceMetadataAdapter
from rag_api.persistence import AppDataStore
from rag_api.services.topic_sync import reconcile_topics_from_sources

logger = logging.getLogger("sync_worker.topics")


def refresh_app_topics_from_sources(settings: AppSettings) -> int:
    store = AppDataStore(settings)
    store.ensure_schema()
    records = reconcile_topics_from_sources(
        PostgresSourceMetadataAdapter(settings),
        store,
        settings,
        prune_stale=True,
    )
    logger.info("event=app_topics_refreshed count=%s", len(records))
    return len(records)
