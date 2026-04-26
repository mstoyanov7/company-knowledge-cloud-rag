from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from shared_schemas import AppSettings, OneNoteCheckpoint, SyncMode, SyncReport

from graph_connectors.onenote.connector import OneNoteConnector
from graph_connectors.onenote.models import OneNotePage, OneNoteSite
from sync_worker.ingestion import DeterministicEmbedder, TextChunker
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer
from sync_worker.onenote.parser import OneNoteHtmlParser, OneNoteResourceHook
from sync_worker.persistence.ports import MetadataStorePort, VectorStorePort

try:
    from opentelemetry import metrics
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    metrics = None


class OneNoteSyncService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        connector: OneNoteConnector,
        parser: OneNoteHtmlParser,
        normalizer: OneNoteDocumentNormalizer,
        chunker: TextChunker,
        embedder: DeterministicEmbedder,
        metadata_store: MetadataStorePort,
        vector_store: VectorStorePort,
        resource_hook: OneNoteResourceHook,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.connector = connector
        self.parser = parser
        self.normalizer = normalizer
        self.chunker = chunker
        self.embedder = embedder
        self.metadata_store = metadata_store
        self.vector_store = vector_store
        self.resource_hook = resource_hook
        self.logger = logger or logging.getLogger("sync_worker.onenote")
        meter = metrics.get_meter("sync_worker.onenote") if metrics else None
        self.sync_latency_ms = meter.create_histogram("onenote_sync_latency_ms") if meter else None
        self.items_counter = meter.create_counter("onenote_sync_items_total") if meter else None

    def bootstrap(self) -> SyncReport:
        return self._sync(SyncMode.bootstrap)

    def incremental(self) -> SyncReport:
        checkpoint = self.metadata_store.get_onenote_checkpoint(self.settings.onenote_scope_key)
        if checkpoint is None or checkpoint.last_modified_cursor_utc is None:
            self.logger.warning(
                "event=onenote_incremental_missing_checkpoint scope=%s action=bootstrap_fallback",
                self.settings.onenote_scope_key,
            )
            return self._sync(SyncMode.bootstrap)
        return self._sync(SyncMode.incremental)

    def _sync(self, mode: SyncMode) -> SyncReport:
        started = time.perf_counter()
        self.metadata_store.ensure_schema()
        self.vector_store.ensure_collection()

        site, notebooks, _sections = self.connector.resolve_scope()
        allowed_notebook_ids = {notebook.id for notebook in notebooks}
        checkpoint = self.metadata_store.get_onenote_checkpoint(self.settings.onenote_scope_key)
        modified_since = checkpoint.last_modified_cursor_utc if checkpoint and mode == SyncMode.incremental else None
        last_cursor = modified_since
        next_url: str | None = None
        processed_source_ids: set[str] = set()

        report = SyncReport(job_name=f"onenote_{mode.value}", scope_key=self.settings.onenote_scope_key)
        self.logger.info(
            "event=onenote_sync_started job=%s scope=%s site_id=%s notebook_count=%s mode=%s cursor=%s",
            report.job_name,
            report.scope_key,
            site.id,
            len(notebooks),
            mode,
            modified_since.isoformat() if modified_since else None,
        )

        while True:
            pages, next_url = self.connector.client.list_pages(site.id, modified_since=modified_since, next_url=next_url)
            scoped_pages = [page for page in pages if page.notebook_id in allowed_notebook_ids]
            report.pages_processed += 1
            report.items_seen += len(scoped_pages)
            self.logger.info(
                "event=onenote_page_batch job=%s scope=%s page=%s items=%s next=%s",
                report.job_name,
                report.scope_key,
                report.pages_processed,
                len(scoped_pages),
                bool(next_url),
            )
            for page in scoped_pages:
                processed_source_ids.add(self._source_item_id(page))
                last_cursor = max_timestamp(last_cursor, page.last_modified_utc)
                self._process_page(site=site, page=page, report=report)
            if not next_url:
                break

        self._reconcile_inventory(
            site=site,
            allowed_notebook_ids=allowed_notebook_ids,
            processed_source_ids=processed_source_ids,
            report=report,
        )

        checkpoint = OneNoteCheckpoint(
            scope_key=self.settings.onenote_scope_key,
            sync_mode=mode,
            site_id=site.id,
            notebook_scope=self.settings.graph_onenote_notebook_scope or "",
            last_modified_cursor_utc=last_cursor,
            page_count=report.pages_processed,
            item_count=report.items_seen,
            updated_at_utc=datetime.now(UTC),
        )
        self.metadata_store.upsert_onenote_checkpoint(checkpoint)
        report.checkpoint = checkpoint

        self.logger.info(
            "event=onenote_sync_completed job=%s scope=%s items_seen=%s changed=%s skipped=%s deleted=%s chunks_written=%s cursor=%s",
            report.job_name,
            report.scope_key,
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
            checkpoint.last_modified_cursor_utc.isoformat() if checkpoint.last_modified_cursor_utc else None,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        if self.sync_latency_ms:
            self.sync_latency_ms.record(duration_ms, {"mode": mode.value})
        if self.items_counter:
            for state, value in [
                ("seen", report.items_seen),
                ("changed", report.items_changed),
                ("skipped", report.items_skipped),
                ("deleted", report.items_deleted),
            ]:
                self.items_counter.add(value, {"mode": mode.value, "state": state})
        return report

    def _process_page(self, *, site: OneNoteSite, page: OneNotePage, report: SyncReport) -> None:
        html = self.connector.client.get_page_content(page.content_url)
        parsed = self.parser.parse(html)
        self.resource_hook.handle_resources(page.id, parsed.resources)
        document = self.normalizer.normalize(site=site, page=page, parsed_page=parsed)
        existing = self.metadata_store.get_source_document(document.source_item_id)

        if existing and not self._document_changed(existing, document):
            if existing.last_modified_utc != document.last_modified_utc:
                self.metadata_store.upsert_source_document(self.settings.onenote_scope_key, document)
            report.items_skipped += 1
            self.logger.info(
                "event=onenote_page_skipped reason=unchanged scope=%s page_id=%s hash=%s",
                self.settings.onenote_scope_key,
                page.id,
                document.content_hash,
            )
            return

        chunks = self.chunker.chunk(document)
        embeddings = self.embedder.embed_chunks(chunks)
        self.metadata_store.upsert_source_document(self.settings.onenote_scope_key, document)
        self.metadata_store.replace_chunks(self.settings.onenote_scope_key, document.source_item_id, chunks)
        self.vector_store.delete_chunks_for_source_item(document.source_item_id)
        self.vector_store.upsert_chunks(chunks, embeddings)
        report.items_changed += 1
        report.chunks_written += len(chunks)
        self.logger.info(
            "event=onenote_page_indexed scope=%s page_id=%s chunks=%s hash=%s",
            self.settings.onenote_scope_key,
            page.id,
            len(chunks),
            document.content_hash,
        )

    def _reconcile_inventory(
        self,
        *,
        site: OneNoteSite,
        allowed_notebook_ids: set[str],
        processed_source_ids: set[str],
        report: SyncReport,
    ) -> None:
        inventory_pages = self._list_all_scoped_pages(site.id, allowed_notebook_ids)
        current_source_ids = {self._source_item_id(page) for page in inventory_pages}
        inventory_by_source_id = {self._source_item_id(page): page for page in inventory_pages}
        stored_documents = self.metadata_store.list_active_source_documents(self.settings.onenote_scope_key, "onenote")

        for document in stored_documents:
            if document.source_item_id not in current_source_ids:
                self.metadata_store.mark_source_deleted(self.settings.onenote_scope_key, document.source_item_id)
                self.vector_store.delete_chunks_for_source_item(document.source_item_id)
                report.items_deleted += 1
                self.logger.info(
                    "event=onenote_page_deleted scope=%s source_item_id=%s title=%s",
                    self.settings.onenote_scope_key,
                    document.source_item_id,
                    document.title,
                )

        for source_item_id, page in inventory_by_source_id.items():
            if source_item_id in processed_source_ids:
                continue
            existing = next((doc for doc in stored_documents if doc.source_item_id == source_item_id), None)
            if existing and self._page_metadata_changed(existing, page):
                self.logger.info(
                    "event=onenote_page_reconcile_update scope=%s page_id=%s reason=metadata_changed",
                    self.settings.onenote_scope_key,
                    page.id,
                )
                self._process_page(site=site, page=page, report=report)

    def _list_all_scoped_pages(self, site_id: str, allowed_notebook_ids: set[str]) -> list[OneNotePage]:
        pages: list[OneNotePage] = []
        next_url: str | None = None
        while True:
            batch, next_url = self.connector.client.list_pages(site_id, next_url=next_url)
            pages.extend(page for page in batch if page.notebook_id in allowed_notebook_ids)
            if not next_url:
                break
        return pages

    def _document_changed(self, existing, current) -> bool:
        return any(
            [
                existing.content_hash != current.content_hash,
                existing.title != current.title,
                existing.section_path != current.section_path,
                existing.source_url != current.source_url,
                existing.metadata.get("section_id") != current.metadata.get("section_id"),
                existing.metadata.get("notebook_id") != current.metadata.get("notebook_id"),
                existing.metadata.get("page_order") != current.metadata.get("page_order"),
            ]
        )

    def _page_metadata_changed(self, existing, page: OneNotePage) -> bool:
        return any(
            [
                existing.title != page.title,
                existing.source_url != page.web_url,
                existing.section_path != f"{page.notebook_name} / {page.section_name}",
                existing.metadata.get("section_id") != page.section_id,
                existing.metadata.get("notebook_id") != page.notebook_id,
                existing.metadata.get("page_order") != page.page_order,
            ]
        )

    def _source_item_id(self, page: OneNotePage) -> str:
        return f"onenote:{page.id}"


def max_timestamp(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)
