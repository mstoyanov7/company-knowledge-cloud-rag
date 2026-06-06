from __future__ import annotations

import re

from shared_schemas import AppSettings, ChunkDocument, SourceDocument

from sync_worker.ingestion.structure import PROCEDURE_KINDS, Section, parse_sections


class TextChunker:
    """Structure-aware chunker.

    Splits a page by headings and never breaks inside a word, fenced code
    block, table row, or list item. Procedure sections are kept together and a
    combined ``procedure`` chunk is emitted for setup-style pages so that
    "how to setup ..." questions retrieve the full procedure in one chunk.
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        chunk_size_chars: int | None = None,
        chunk_overlap_chars: int | None = None,
        procedure_chunk_max_chars: int | None = None,
    ) -> None:
        self.settings = settings
        self.chunk_size_chars = chunk_size_chars or settings.onenote_chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars or settings.onenote_chunk_overlap_chars
        self.procedure_chunk_max_chars = (
            procedure_chunk_max_chars or settings.onenote_procedure_chunk_max_chars
        )

    def chunk(self, document: SourceDocument) -> list[ChunkDocument]:
        content = document.content_text.strip()
        if not content:
            return []

        sections = parse_sections(content)
        if not sections:
            return []

        pieces: list[tuple[str, str]] = []  # (text, chunk_kind)
        has_body_section = any(section.kind not in {"metadata"} and section.body for section in sections)

        for section in sections:
            # Rule 8: do not emit title/metadata-only chunks when real content exists.
            if section.kind == "metadata" and has_body_section and not section.body:
                continue
            for text in self._split_section(section):
                pieces.append((text, section.kind))

        combined = self._combined_procedure_chunk(sections)
        if combined is not None:
            # Strong combined procedure chunk goes first so it ranks well.
            pieces.insert(0, (combined, "procedure"))

        chunks: list[ChunkDocument] = []
        for chunk_index, (text, kind) in enumerate(pieces):
            chunks.append(self._build_chunk(document, text, kind, chunk_index))
        return chunks

    def _split_section(self, section: Section) -> list[str]:
        """Split a section into chunks at block boundaries, never mid-block."""

        text = section.text
        if len(text) <= self.chunk_size_chars:
            return [text] if text else []

        heading = section.heading or ""
        blocks = section.blocks
        chunks: list[str] = []
        current: list[str] = []
        current_len = len(heading)

        def flush() -> None:
            if current:
                parts = [heading, *current] if heading else list(current)
                chunks.append("\n\n".join(part for part in parts if part).strip())

        for block in blocks:
            block_len = len(block) + 2
            if current and current_len + block_len > self.chunk_size_chars:
                flush()
                # Block-level overlap: repeat the trailing block if it is small.
                tail = current[-1]
                current = [tail] if len(tail) <= self.chunk_overlap_chars else []
                current_len = len(heading) + sum(len(item) + 2 for item in current)
            if len(block) > self.chunk_size_chars and not block.startswith("```"):
                # Oversized prose block: split on sentence boundaries (never words).
                for sentence_block in _split_oversized_block(block, self.chunk_size_chars):
                    current.append(sentence_block)
                    current_len += len(sentence_block) + 2
                    flush()
                    current = []
                    current_len = len(heading)
                continue
            current.append(block)
            current_len += block_len
        flush()
        return [chunk for chunk in chunks if chunk]

    def _combined_procedure_chunk(self, sections: list[Section]) -> str | None:
        procedure_sections = [section for section in sections if section.kind in PROCEDURE_KINDS]
        kinds_present = {section.kind for section in procedure_sections}
        # Only worthwhile when the page is a multi-step procedure.
        if len(kinds_present) < 2:
            return None

        ordered = sorted(
            procedure_sections,
            key=lambda section: PROCEDURE_KINDS.index(section.kind),
        )
        parts: list[str] = []
        total = 0
        for section in ordered:
            section_text = section.text
            if total + len(section_text) > self.procedure_chunk_max_chars and parts:
                break
            parts.append(section_text)
            total += len(section_text) + 2
        if not parts:
            return None
        return "\n\n".join(parts).strip()

    def _build_chunk(self, document: SourceDocument, text: str, kind: str, chunk_index: int) -> ChunkDocument:
        metadata = dict(document.metadata)
        metadata["chunk_kind"] = kind
        return ChunkDocument(
            tenant_id=document.tenant_id,
            source_system=document.source_system,
            source_container=document.source_container,
            source_item_id=document.source_item_id,
            source_url=document.source_url,
            title=document.title,
            section_path=document.section_path,
            last_modified_utc=document.last_modified_utc,
            acl_tags=document.acl_tags,
            acl_bindings=document.acl_bindings,
            content_hash=document.content_hash,
            chunk_id=f"{document.source_item_id}-chunk-{chunk_index}",
            chunk_index=chunk_index,
            chunk_text=text,
            chunk_kind=kind,
            embedding_model=self.settings.default_embedding_provider,
            language=document.language,
            tags=document.tags,
            metadata=metadata,
        )


def _split_oversized_block(block: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", block)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [block]
