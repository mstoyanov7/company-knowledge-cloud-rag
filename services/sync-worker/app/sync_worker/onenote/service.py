from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
from uuid import NAMESPACE_URL, uuid5

from shared_schemas import AppSettings, OneNoteCheckpoint, SourceAttachment, SourceDocument, SyncMode, SyncReport

from graph_connectors.onenote.connector import OneNoteConnector
from graph_connectors.onenote.models import OneNotePage, OneNoteSection, OneNoteSite
from sync_worker.ingestion import (
    CompositeFileExtractor,
    DeterministicEmbedder,
    READABLE_ATTACHMENT_EXTENSIONS,
    TextChunker,
    compute_bytes_hash,
    compute_content_hash,
)
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer
from sync_worker.onenote.parser import OneNoteHtmlParser, OneNoteResourceHook, OneNoteResourceRef
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
        file_extractor: CompositeFileExtractor | None = None,
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
        self.file_extractor = file_extractor or CompositeFileExtractor()
        self.logger = logger or logging.getLogger("sync_worker.onenote")
        meter = metrics.get_meter("sync_worker.onenote") if metrics else None
        self.sync_latency_ms = meter.create_histogram("onenote_sync_latency_ms") if meter else None
        self.items_counter = meter.create_counter("onenote_sync_items_total") if meter else None

    def bootstrap(self) -> SyncReport:
        return self._sync(SyncMode.bootstrap, reconcile_inventory=True)

    def incremental(self) -> SyncReport:
        self._ensure_storage()
        checkpoint = self.metadata_store.get_onenote_checkpoint(self.settings.onenote_scope_key)
        if checkpoint is None or checkpoint.last_modified_cursor_utc is None:
            self.logger.warning(
                "event=onenote_incremental_missing_checkpoint scope=%s action=bootstrap_fallback",
                self.settings.onenote_scope_key,
            )
            return self._sync(SyncMode.bootstrap, reconcile_inventory=True)
        return self._sync(SyncMode.incremental, reconcile_inventory=False)

    def reconciliation(self) -> SyncReport:
        self._ensure_storage()
        checkpoint = self.metadata_store.get_onenote_checkpoint(self.settings.onenote_scope_key)
        if checkpoint is None or checkpoint.last_modified_cursor_utc is None:
            self.logger.warning(
                "event=onenote_reconciliation_missing_checkpoint scope=%s action=bootstrap_fallback",
                self.settings.onenote_scope_key,
            )
            return self._sync(SyncMode.bootstrap, reconcile_inventory=True)
        return self._sync(SyncMode.incremental, reconcile_inventory=True)

    def _sync(self, mode: SyncMode, *, reconcile_inventory: bool) -> SyncReport:
        started = time.perf_counter()
        self._ensure_storage()

        site, notebooks, sections = self.connector.resolve_scope()
        allowed_notebook_ids = {notebook.id for notebook in notebooks}
        scoped_sections = [section for section in sections if section.notebook_id in allowed_notebook_ids]
        checkpoint = self.metadata_store.get_onenote_checkpoint(self.settings.onenote_scope_key)
        checkpoint_cursor = checkpoint.last_modified_cursor_utc if checkpoint else None
        modified_since = self._modified_since_for_mode(mode, checkpoint_cursor)
        last_cursor = checkpoint_cursor if mode == SyncMode.incremental else None
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

        for section in scoped_sections:
            next_url = None
            while True:
                pages, next_url = self.connector.client.list_pages(
                    site.id,
                    section_id=section.id,
                    modified_since=modified_since,
                    next_url=next_url,
                )
                scoped_pages = [page for page in pages if page.notebook_id in allowed_notebook_ids]
                report.pages_processed += 1
                report.items_seen += len(scoped_pages)
                self.logger.info(
                    "event=onenote_page_batch job=%s scope=%s section_id=%s page=%s items=%s next=%s",
                    report.job_name,
                    report.scope_key,
                    section.id,
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

        if not scoped_sections:
            self.logger.info(
                "event=onenote_no_sections job=%s scope=%s site_id=%s",
                report.job_name,
                report.scope_key,
                site.id,
            )

        if reconcile_inventory:
            self._reconcile_inventory(
                site=site,
                sections=scoped_sections,
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
        document = self.normalizer.normalize(
            site=site,
            page=page,
            parsed_page=parsed,
            embedding_model=self.settings.default_embedding_provider,
        )
        attachment_refs, attachment_changed = self._process_attachments(
            parent_document=document,
            resources=parsed.resources,
            report=report,
        )
        if attachment_refs:
            metadata = dict(document.metadata)
            metadata["attachment_refs"] = [_attachment_link_payload(attachment) for attachment in attachment_refs]
            document = document.model_copy(update={"metadata": metadata})
        existing = self.metadata_store.get_source_document(document.source_item_id)

        if existing and not self._document_changed(existing, document) and not attachment_changed:
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

    def _process_attachments(
        self,
        *,
        parent_document: SourceDocument,
        resources: list[OneNoteResourceRef],
        report: SyncReport,
    ) -> tuple[list[SourceAttachment], bool]:
        attachments: list[SourceAttachment] = []
        changed = False

        for resource in resources:
            if resource.resource_type != "attachment":
                continue
            attachment, attachment_changed = self._process_attachment(parent_document, resource, report)
            attachments.append(attachment)
            changed = changed or attachment_changed

        active_download_ids = {attachment.download_id for attachment in attachments}
        stale = self.metadata_store.mark_stale_attachments_deleted(
            self.settings.onenote_scope_key,
            parent_document.source_item_id,
            active_download_ids,
        )
        for attachment in stale:
            if attachment.indexed_source_item_id:
                self.metadata_store.mark_source_deleted(
                    self.settings.onenote_scope_key,
                    attachment.indexed_source_item_id,
                )
                self.vector_store.delete_chunks_for_source_item(attachment.indexed_source_item_id)
                changed = True
        return attachments, changed

    def _process_attachment(
        self,
        parent_document: SourceDocument,
        resource: OneNoteResourceRef,
        report: SyncReport,
    ) -> tuple[SourceAttachment, bool]:
        file_name = _safe_file_name(resource.name or _resource_file_name(resource.resource_url))
        file_extension = PurePosixPath(file_name).suffix.lower()
        download_id = _download_id(parent_document.source_item_id, resource.resource_url, file_name)
        existing = self.metadata_store.get_source_attachment(download_id)
        content: bytes | None = None
        content_hash = _metadata_hash(resource.resource_url)
        storage_path: str | None = None
        size_bytes = 0
        metadata: dict[str, object] = {
            "resource_origin": resource.resource_origin,
            "download_url": _download_url(download_id) if resource.resource_origin != "link" else resource.resource_url,
        }

        if resource.resource_origin != "link":
            content = self.connector.client.get_resource_content(resource.resource_url)
            content_hash = compute_bytes_hash(content)
            size_bytes = len(content)
            storage_path = self._store_attachment_bytes(
                download_id=download_id,
                file_name=file_name,
                content_hash=content_hash,
                content=content,
            )

        readable = False
        indexed_source_item_id: str | None = None
        if content is not None and file_extension in READABLE_ATTACHMENT_EXTENSIONS:
            indexed_source_item_id, readable = self._index_readable_attachment(
                parent_document=parent_document,
                resource=resource,
                download_id=download_id,
                file_name=file_name,
                file_extension=file_extension,
                content=content,
                content_hash=content_hash,
                storage_path=storage_path,
                size_bytes=size_bytes,
                report=report,
                metadata=metadata,
            )

        attachment = SourceAttachment(
            download_id=download_id,
            tenant_id=parent_document.tenant_id,
            source_system=parent_document.source_system,
            source_container=parent_document.source_container,
            parent_source_item_id=parent_document.source_item_id,
            parent_title=parent_document.title,
            source_url=parent_document.source_url,
            resource_url=resource.resource_url,
            file_name=file_name,
            file_extension=file_extension.lstrip("."),
            mime_type=resource.mime_type,
            size_bytes=size_bytes,
            readable=readable,
            indexed_source_item_id=indexed_source_item_id,
            storage_path=storage_path,
            content_hash=content_hash,
            last_modified_utc=parent_document.last_modified_utc,
            acl_tags=parent_document.acl_tags,
            acl_bindings=parent_document.acl_bindings,
            metadata=metadata,
        )
        self.metadata_store.upsert_source_attachment(self.settings.onenote_scope_key, attachment)
        changed = existing is None or existing.content_hash != attachment.content_hash or existing.indexed_source_item_id != indexed_source_item_id
        return attachment, changed

    def _index_readable_attachment(
        self,
        *,
        parent_document: SourceDocument,
        resource: OneNoteResourceRef,
        download_id: str,
        file_name: str,
        file_extension: str,
        content: bytes,
        content_hash: str,
        storage_path: str | None,
        size_bytes: int,
        report: SyncReport,
        metadata: dict[str, object],
    ) -> tuple[str | None, bool]:
        try:
            extracted = self.file_extractor.extract(file_name, content, resource.mime_type)
        except Exception as error:
            metadata["extraction_error"] = str(error)
            return None, False

        text = extracted.text.strip()
        if not text:
            metadata["extraction_error"] = "No extractable text."
            return None, False

        indexed_source_item_id = f"onenote-attachment:{download_id}"
        attachment_metadata = {
            **parent_document.metadata,
            **metadata,
            "document_kind": "attachment",
            "download_id": download_id,
            "download_url": _download_url(download_id),
            "indexed_source_item_id": indexed_source_item_id,
            "readable": True,
            "parent_source_item_id": parent_document.source_item_id,
            "parent_title": parent_document.title,
            "parent_source_url": parent_document.source_url,
            "attachment_file_name": file_name,
            "attachment_file_extension": file_extension.lstrip("."),
            "attachment_size_bytes": size_bytes,
            "attachment_storage_path": storage_path,
            "extractor_name": extracted.extractor_name,
            "extractor_metadata": extracted.metadata,
        }
        # Carry the parent page title into the attachment's searchable title and
        # section so a question that names the page (e.g. "ModelViewer") matches
        # the attachment's content even when the page body is empty and the file
        # text never mentions the page name. Without this the page title is lost
        # (title would be just "readme.md") and the question drifts to other pages.
        parent_title = parent_document.title or ""
        if parent_title and parent_title.lower() not in file_name.lower():
            attachment_title = f"{parent_title} - {file_name}"
        else:
            attachment_title = file_name
        document = SourceDocument(
            tenant_id=parent_document.tenant_id,
            source_system=parent_document.source_system,
            source_container=parent_document.source_container,
            source_item_id=indexed_source_item_id,
            source_url=_download_url(download_id),
            title=attachment_title,
            file_name=file_name,
            file_extension=file_extension.lstrip("."),
            mime_type=resource.mime_type,
            section_path=f"{parent_document.section_path or parent_document.title} / {parent_document.title} / Attachments",
            last_modified_utc=parent_document.last_modified_utc,
            acl_tags=parent_document.acl_tags,
            acl_bindings=parent_document.acl_bindings,
            content_hash=compute_content_hash(text),
            content_text=text,
            language=parent_document.language,
            tags=list(dict.fromkeys([*parent_document.tags, "attachment", f"attachment:{file_extension.lstrip('.')}"])),
            metadata=attachment_metadata,
        )
        existing = self.metadata_store.get_source_document(indexed_source_item_id)
        if existing and not self._document_changed(existing, document):
            self.metadata_store.upsert_source_document(self.settings.onenote_scope_key, document)
            return indexed_source_item_id, True

        chunks = self.chunker.chunk(document)
        embeddings = self.embedder.embed_chunks(chunks)
        self.metadata_store.upsert_source_document(self.settings.onenote_scope_key, document)
        self.metadata_store.replace_chunks(self.settings.onenote_scope_key, document.source_item_id, chunks)
        self.vector_store.delete_chunks_for_source_item(document.source_item_id)
        self.vector_store.upsert_chunks(chunks, embeddings)
        report.chunks_written += len(chunks)
        return indexed_source_item_id, True

    def _store_attachment_bytes(
        self,
        *,
        download_id: str,
        file_name: str,
        content_hash: str,
        content: bytes,
    ) -> str:
        extension = PurePosixPath(file_name).suffix.lower() or ".bin"
        relative = Path(content_hash[:2]) / f"{download_id}{extension}"
        root = Path(self.settings.attachment_storage_dir)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
        return relative.as_posix()

    def _reconcile_inventory(
        self,
        *,
        site: OneNoteSite,
        sections: list[OneNoteSection],
        allowed_notebook_ids: set[str],
        processed_source_ids: set[str],
        report: SyncReport,
    ) -> None:
        inventory_pages = self._list_all_scoped_pages(site.id, sections, allowed_notebook_ids)
        current_source_ids = {self._source_item_id(page) for page in inventory_pages}
        inventory_by_source_id = {self._source_item_id(page): page for page in inventory_pages}
        stored_documents = [
            document
            for document in self.metadata_store.list_active_source_documents(self.settings.onenote_scope_key, "onenote")
            if document.metadata.get("document_kind") != "attachment"
        ]

        for document in stored_documents:
            if document.source_item_id not in current_source_ids:
                for attachment in self.metadata_store.list_active_source_attachments(
                    self.settings.onenote_scope_key,
                    [document.source_item_id],
                ):
                    if attachment.indexed_source_item_id:
                        self.metadata_store.mark_source_deleted(
                            self.settings.onenote_scope_key,
                            attachment.indexed_source_item_id,
                        )
                        self.vector_store.delete_chunks_for_source_item(attachment.indexed_source_item_id)
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

    def _list_all_scoped_pages(
        self,
        site_id: str,
        sections: list[OneNoteSection],
        allowed_notebook_ids: set[str],
    ) -> list[OneNotePage]:
        pages: list[OneNotePage] = []
        for section in sections:
            next_url: str | None = None
            while True:
                batch, next_url = self.connector.client.list_pages(site_id, section_id=section.id, next_url=next_url)
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
                existing.metadata.get("embedding_model") != current.metadata.get("embedding_model"),
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

    def _modified_since_for_mode(self, mode: SyncMode, checkpoint_cursor: datetime | None) -> datetime | None:
        if mode != SyncMode.incremental or checkpoint_cursor is None:
            return None
        lookback_seconds = max(0, self.settings.onenote_incremental_lookback_seconds)
        if lookback_seconds <= 0:
            return checkpoint_cursor
        return checkpoint_cursor - timedelta(seconds=lookback_seconds)

    def _ensure_storage(self) -> None:
        self.metadata_store.ensure_schema()
        self.vector_store.ensure_collection()


def max_timestamp(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)


def _download_id(parent_source_item_id: str, resource_url: str, file_name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{parent_source_item_id}:{resource_url}:{file_name}"))


def _download_url(download_id: str) -> str:
    return f"/api/v1/attachments/{download_id}/download"


def _metadata_hash(value: str) -> str:
    return compute_bytes_hash(value.encode("utf-8"))


def _resource_file_name(resource_url: str) -> str:
    parsed = urlparse(resource_url)
    name = PurePosixPath(unquote(parsed.path or resource_url)).name
    return name or "attachment.bin"


def _safe_file_name(file_name: str) -> str:
    base = PurePosixPath(file_name.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return cleaned or "attachment.bin"


def _attachment_link_payload(attachment: SourceAttachment) -> dict[str, object]:
    return {
        "download_id": attachment.download_id,
        "file_name": attachment.file_name,
        "mime_type": attachment.mime_type,
        "file_extension": attachment.file_extension,
        "size_bytes": attachment.size_bytes,
        "readable": attachment.readable,
        "parent_source_item_id": attachment.parent_source_item_id,
        "parent_title": attachment.parent_title,
        "download_url": _download_url(attachment.download_id) if attachment.storage_path else attachment.resource_url,
        "indexed_source_item_id": attachment.indexed_source_item_id,
    }
