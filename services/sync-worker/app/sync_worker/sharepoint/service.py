from __future__ import annotations

import logging
from datetime import UTC, datetime

from shared_schemas import AppSettings, SharePointCheckpoint, SyncMode, SyncReport

from graph_connectors.sharepoint.connector import SharePointConnector
from sync_worker.ingestion import CompositeFileExtractor, DeterministicEmbedder, TextChunker, UnsupportedFileTypeError
from sync_worker.sharepoint.normalization import SharePointDocumentNormalizer
from sync_worker.sharepoint.ports import MetadataStorePort, VectorStorePort


class SharePointSyncService:
    def __init__(
        self,
        *,
        settings: AppSettings,
        connector: SharePointConnector,
        extractor: CompositeFileExtractor,
        normalizer: SharePointDocumentNormalizer,
        chunker: TextChunker,
        embedder: DeterministicEmbedder,
        metadata_store: MetadataStorePort,
        vector_store: VectorStorePort,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.connector = connector
        self.extractor = extractor
        self.normalizer = normalizer
        self.chunker = chunker
        self.embedder = embedder
        self.metadata_store = metadata_store
        self.vector_store = vector_store
        self.logger = logger or logging.getLogger("sync_worker.sharepoint")

    def bootstrap(self) -> SyncReport:
        return self._sync(SyncMode.bootstrap)

    def incremental(self) -> SyncReport:
        checkpoint = self.metadata_store.get_checkpoint(self.settings.sharepoint_scope_key)
        if checkpoint is None or (checkpoint.delta_link is None and checkpoint.cursor_url is None):
            self.logger.warning(
                "event=sharepoint_incremental_missing_checkpoint scope=%s action=bootstrap_fallback",
                self.settings.sharepoint_scope_key,
            )
            return self._sync(SyncMode.bootstrap)
        return self._sync(SyncMode.incremental)

    def _sync(self, mode: SyncMode) -> SyncReport:
        self.metadata_store.ensure_schema()
        self.vector_store.ensure_collection()

        site, drive = self.connector.resolve_scope()
        scope_key = self.settings.sharepoint_scope_key
        checkpoint = self.metadata_store.get_checkpoint(scope_key)
        cursor_url = checkpoint.cursor_url if checkpoint else None
        delta_link = checkpoint.delta_link if checkpoint and mode == SyncMode.incremental and not cursor_url else None

        report = SyncReport(job_name=f"sharepoint_{mode.value}", scope_key=scope_key)
        self.logger.info(
            "event=sharepoint_sync_started job=%s scope=%s site_id=%s drive_id=%s mode=%s",
            report.job_name,
            scope_key,
            site.id,
            drive.id,
            mode,
        )

        while True:
            page = self.connector.client.get_drive_delta_page(
                drive.id,
                cursor_url=cursor_url,
                delta_link=delta_link,
            )
            report.pages_processed += 1
            report.items_seen += len(page.items)
            self.logger.info(
                "event=sharepoint_delta_page job=%s scope=%s page=%s items=%s next=%s delta=%s",
                report.job_name,
                scope_key,
                report.pages_processed,
                len(page.items),
                bool(page.next_link),
                bool(page.delta_link),
            )

            for item in page.items:
                self._process_item(site=site, drive=drive, item=item, report=report)

            checkpoint = SharePointCheckpoint(
                scope_key=scope_key,
                sync_mode=mode,
                site_id=site.id,
                drive_id=drive.id,
                cursor_url=page.next_link,
                delta_link=page.delta_link if not page.next_link else (checkpoint.delta_link if checkpoint else None),
                page_count=report.pages_processed,
                item_count=report.items_seen,
                updated_at_utc=datetime.now(UTC),
            )
            self.metadata_store.upsert_checkpoint(checkpoint)
            report.checkpoint = checkpoint

            if not page.next_link:
                break
            cursor_url = page.next_link
            delta_link = None

        self.logger.info(
            "event=sharepoint_sync_completed job=%s scope=%s items_seen=%s changed=%s skipped=%s deleted=%s chunks_written=%s",
            report.job_name,
            scope_key,
            report.items_seen,
            report.items_changed,
            report.items_skipped,
            report.items_deleted,
            report.chunks_written,
        )
        return report

    def _process_item(self, *, site, drive, item, report: SyncReport) -> None:
        if item.is_deleted:
            self.metadata_store.mark_source_deleted(self.settings.sharepoint_scope_key, item.id, item.last_modified_utc)
            self.vector_store.delete_chunks_for_source_item(item.id)
            report.items_deleted += 1
            self.logger.info(
                "event=sharepoint_item_deleted scope=%s item_id=%s title=%s",
                self.settings.sharepoint_scope_key,
                item.id,
                item.name,
            )
            return

        if not item.is_file:
            report.items_skipped += 1
            self.logger.info(
                "event=sharepoint_item_skipped reason=not_file scope=%s item_id=%s title=%s",
                self.settings.sharepoint_scope_key,
                item.id,
                item.name,
            )
            return

        file_bytes = self.connector.client.download_file(drive.id, item.id)
        try:
            extracted_content = self.extractor.extract(item.file_name, file_bytes, item.mime_type)
        except UnsupportedFileTypeError:
            report.items_skipped += 1
            self.logger.info(
                "event=sharepoint_item_skipped reason=unsupported_file scope=%s item_id=%s title=%s extension=%s",
                self.settings.sharepoint_scope_key,
                item.id,
                item.name,
                item.file_extension,
            )
            return

        document = self.normalizer.normalize(
            site=site,
            drive=drive,
            item=item,
            extracted_content=extracted_content,
        )
        existing = self.metadata_store.get_source_document(item.id)
        if existing and existing.content_hash == document.content_hash:
            self.metadata_store.upsert_source_document(self.settings.sharepoint_scope_key, document)
            report.items_skipped += 1
            self.logger.info(
                "event=sharepoint_item_skipped reason=unchanged scope=%s item_id=%s hash=%s",
                self.settings.sharepoint_scope_key,
                item.id,
                document.content_hash,
            )
            return

        chunks = self.chunker.chunk(document)
        embeddings = self.embedder.embed_chunks(chunks)

        self.metadata_store.upsert_source_document(self.settings.sharepoint_scope_key, document)
        self.metadata_store.replace_chunks(self.settings.sharepoint_scope_key, item.id, chunks)
        self.vector_store.delete_chunks_for_source_item(item.id)
        self.vector_store.upsert_chunks(chunks, embeddings)

        report.items_changed += 1
        report.chunks_written += len(chunks)
        self.logger.info(
            "event=sharepoint_item_indexed scope=%s item_id=%s chunks=%s hash=%s",
            self.settings.sharepoint_scope_key,
            item.id,
            len(chunks),
            document.content_hash,
        )
