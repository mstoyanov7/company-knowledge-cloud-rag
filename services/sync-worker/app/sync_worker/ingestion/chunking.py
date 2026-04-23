from __future__ import annotations

from shared_schemas import AppSettings, ChunkDocument, SourceDocument


class TextChunker:
    def __init__(
        self,
        settings: AppSettings,
        *,
        chunk_size_chars: int | None = None,
        chunk_overlap_chars: int | None = None,
    ) -> None:
        self.settings = settings
        self.chunk_size_chars = chunk_size_chars or settings.sharepoint_chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars or settings.sharepoint_chunk_overlap_chars

    def chunk(self, document: SourceDocument) -> list[ChunkDocument]:
        content = document.content_text.strip()
        if not content:
            return []

        chunk_size = self.chunk_size_chars
        overlap = self.chunk_overlap_chars
        chunks: list[ChunkDocument] = []
        start = 0
        chunk_index = 0

        while start < len(content):
            end = min(len(content), start + chunk_size)
            chunk_text = content[start:end].strip()
            if chunk_text:
                chunks.append(
                    ChunkDocument(
                        tenant_id=document.tenant_id,
                        source_system=document.source_system,
                        source_container=document.source_container,
                        source_item_id=document.source_item_id,
                        source_url=document.source_url,
                        title=document.title,
                        section_path=document.section_path,
                        last_modified_utc=document.last_modified_utc,
                        acl_tags=document.acl_tags,
                        content_hash=document.content_hash,
                        chunk_id=f"{document.source_item_id}-chunk-{chunk_index}",
                        chunk_index=chunk_index,
                        chunk_text=chunk_text,
                        embedding_model=self.settings.default_embedding_provider,
                        language=document.language,
                        tags=document.tags,
                        metadata=document.metadata,
                    )
                )
                chunk_index += 1
            if end >= len(content):
                break
            start = max(end - overlap, start + 1)
        return chunks
