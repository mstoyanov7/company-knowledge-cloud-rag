from __future__ import annotations

from shared_schemas import AppSettings, SourceAttachment, SourceDocument

from rag_api.adapters.retrieval.mock import MockRetriever


class MockSourceMetadataAdapter:
    name = "mock-source-metadata"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def list_documents(self) -> list[SourceDocument]:
        retriever = MockRetriever(self.settings)
        documents: dict[str, SourceDocument] = {}
        for chunk in retriever.documents:
            existing = documents.get(chunk.source_item_id)
            if existing and existing.last_modified_utc >= chunk.last_modified_utc:
                continue
            documents[chunk.source_item_id] = SourceDocument(
                tenant_id=chunk.tenant_id,
                source_system=chunk.source_system,
                source_container=chunk.source_container,
                source_item_id=chunk.source_item_id,
                source_url=chunk.source_url,
                title=chunk.title,
                file_name=f"{chunk.title}.one",
                file_extension="one",
                mime_type="text/plain",
                section_path=chunk.section_path,
                last_modified_utc=chunk.last_modified_utc,
                acl_tags=chunk.acl_tags,
                acl_bindings=chunk.acl_bindings,
                content_hash=chunk.content_hash,
                content_text=chunk.chunk_text,
                language=chunk.language,
                tags=chunk.tags,
                metadata=chunk.metadata,
            )
        return list(documents.values())

    def list_attachments(self, parent_source_item_ids: list[str] | None = None) -> list[SourceAttachment]:
        return []

    def get_attachment(self, download_id: str) -> SourceAttachment | None:
        return None


class PostgresSourceMetadataAdapter:
    name = "postgres-source-metadata"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def list_documents(self) -> list[SourceDocument]:
        from sync_worker.persistence import PostgresMetadataStore

        store = PostgresMetadataStore(self.settings)
        return store.list_active_source_documents(self.settings.onenote_scope_key, "onenote")

    def list_attachments(self, parent_source_item_ids: list[str] | None = None) -> list[SourceAttachment]:
        from sync_worker.persistence import PostgresMetadataStore

        store = PostgresMetadataStore(self.settings)
        store.ensure_schema()
        return store.list_active_source_attachments(self.settings.onenote_scope_key, parent_source_item_ids)

    def get_attachment(self, download_id: str) -> SourceAttachment | None:
        from sync_worker.persistence import PostgresMetadataStore

        store = PostgresMetadataStore(self.settings)
        store.ensure_schema()
        return store.get_source_attachment(download_id)

