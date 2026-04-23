from __future__ import annotations

from typing import Protocol

from shared_schemas import ChunkDocument, OneNoteCheckpoint, SharePointCheckpoint, SourceDocument


class MetadataStorePort(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get_checkpoint(self, scope_key: str) -> SharePointCheckpoint | None:
        ...

    def upsert_checkpoint(self, checkpoint: SharePointCheckpoint) -> SharePointCheckpoint:
        ...

    def get_onenote_checkpoint(self, scope_key: str) -> OneNoteCheckpoint | None:
        ...

    def upsert_onenote_checkpoint(self, checkpoint: OneNoteCheckpoint) -> OneNoteCheckpoint:
        ...

    def get_source_document(self, source_item_id: str) -> SourceDocument | None:
        ...

    def upsert_source_document(self, scope_key: str, document: SourceDocument) -> None:
        ...

    def mark_source_deleted(self, scope_key: str, source_item_id: str, deleted_at_utc=None) -> None:
        ...

    def replace_chunks(self, scope_key: str, source_item_id: str, chunks: list[ChunkDocument]) -> None:
        ...

    def list_active_source_documents(self, scope_key: str, source_system: str) -> list[SourceDocument]:
        ...


class VectorStorePort(Protocol):
    def ensure_collection(self) -> None:
        ...

    def upsert_chunks(self, chunks: list[ChunkDocument], embeddings: list[list[float]]) -> None:
        ...

    def delete_chunks_for_source_item(self, source_item_id: str) -> None:
        ...
