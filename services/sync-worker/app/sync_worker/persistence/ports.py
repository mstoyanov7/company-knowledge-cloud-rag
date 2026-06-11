from __future__ import annotations

from typing import Protocol

from shared_schemas import ChunkDocument, OneNoteCheckpoint, SourceAttachment, SourceDocument


class MetadataStorePort(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get_onenote_checkpoint(self, scope_key: str) -> OneNoteCheckpoint | None:
        ...

    def upsert_onenote_checkpoint(self, checkpoint: OneNoteCheckpoint) -> OneNoteCheckpoint:
        ...

    def get_source_document(self, source_item_id: str) -> SourceDocument | None:
        ...

    def upsert_source_document(self, scope_key: str, document: SourceDocument) -> None:
        ...

    def upsert_source_attachment(self, scope_key: str, attachment: SourceAttachment) -> None:
        ...

    def get_source_attachment(self, download_id: str) -> SourceAttachment | None:
        ...

    def list_active_source_attachments(
        self,
        scope_key: str,
        parent_source_item_ids: list[str] | None = None,
    ) -> list[SourceAttachment]:
        ...

    def mark_stale_attachments_deleted(
        self,
        scope_key: str,
        parent_source_item_id: str,
        active_download_ids: set[str],
    ) -> list[SourceAttachment]:
        ...

    def mark_source_deleted(self, scope_key: str, source_item_id: str, deleted_at_utc=None) -> None:
        ...

    def replace_chunks(self, scope_key: str, source_item_id: str, chunks: list[ChunkDocument]) -> None:
        ...

    def list_active_source_documents(self, scope_key: str, source_system: str) -> list[SourceDocument]:
        ...

    def list_chunks(self, scope_key: str, *, source_system: str = "onenote") -> list[ChunkDocument]:
        ...


class VectorStorePort(Protocol):
    def ensure_collection(self) -> None:
        ...

    def upsert_chunks(self, chunks: list[ChunkDocument], embeddings: list[list[float]]) -> None:
        ...

    def delete_chunks_for_source_item(self, source_item_id: str) -> None:
        ...
