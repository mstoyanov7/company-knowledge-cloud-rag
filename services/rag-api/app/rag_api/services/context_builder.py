from __future__ import annotations

from dataclasses import dataclass
import re

from shared_schemas import ChunkDocument, Citation

from rag_api.services.query_understanding import QuestionAnalysis
from rag_api.services.retrieval_ranking import chunk_kind_of, is_procedure_question

# Canonical ordering of procedure sections in the assembled context.
_PROCEDURE_ORDER = {
    "procedure": 0,
    "overview": 1,
    "prerequisites": 2,
    "install": 3,
    "configuration": 4,
    "run": 5,
    "verification": 6,
    "troubleshooting": 7,
    "checklist": 8,
    "commands": 9,
    "reference": 10,
    "section": 11,
    "table": 12,
    "metadata": 99,
}


@dataclass(frozen=True, slots=True)
class AnswerContextBlock:
    citation_index: int
    title: str
    section_path: str | None
    heading: str | None
    content: str
    source_url: str
    is_attachment: bool = False
    parent_title: str | None = None
    attachment_file_name: str | None = None


@dataclass(frozen=True, slots=True)
class AnswerContext:
    blocks: tuple[AnswerContextBlock, ...]
    context_blocks: tuple[str, ...]
    total_chars: int
    source_titles: tuple[str, ...]


def build_answer_context(
    question_analysis: QuestionAnalysis,
    retrieved_chunks: list[ChunkDocument],
    citations: list[Citation],
    *,
    max_chars: int = 9000,
) -> AnswerContext:
    blocks: list[AnswerContextBlock] = []
    rendered_blocks: list[str] = []
    total_chars = 0

    ordered_pairs = list(zip(retrieved_chunks, citations, strict=False))
    if is_procedure_question(question_analysis):
        # Keep retrieval rank as the tie-breaker, but lay procedure sections out
        # in their natural setup order (overview -> prerequisites -> ... -> run).
        ordered_pairs = sorted(
            enumerate(ordered_pairs),
            key=lambda item: (_PROCEDURE_ORDER.get(chunk_kind_of(item[1][0]) or "section", 11), item[0]),
        )
        ordered_pairs = [pair for _index, pair in ordered_pairs]

    accumulated_norm = ""
    for chunk, citation in ordered_pairs:
        content = _trim_chunk_text(chunk.chunk_text, max_chars=max(400, min(3200, max_chars // 2)))
        normalized_content = re.sub(r"\s+", " ", content).strip()
        # Skip section chunks already fully covered by the combined procedure chunk.
        if normalized_content and normalized_content in accumulated_norm:
            continue
        accumulated_norm = f"{accumulated_norm}\n{normalized_content}"
        chunk_metadata = chunk.metadata or {}
        is_attachment = chunk_metadata.get("document_kind") == "attachment"
        block = AnswerContextBlock(
            citation_index=citation.index,
            title=chunk.title,
            section_path=chunk.section_path,
            heading=_first_heading(chunk.chunk_text),
            content=content,
            source_url=chunk.source_url,
            is_attachment=is_attachment,
            parent_title=str(chunk_metadata.get("parent_title")) if chunk_metadata.get("parent_title") else None,
            attachment_file_name=(
                str(chunk_metadata.get("attachment_file_name")) if chunk_metadata.get("attachment_file_name") else None
            ),
        )
        rendered = _render_block(question_analysis, block)
        if total_chars + len(rendered) > max_chars and rendered_blocks:
            break
        blocks.append(block)
        rendered_blocks.append(rendered)
        total_chars += len(rendered)

    source_titles = tuple(dict.fromkeys(block.title for block in blocks if block.title))
    return AnswerContext(
        blocks=tuple(blocks),
        context_blocks=tuple(rendered_blocks),
        total_chars=total_chars,
        source_titles=source_titles,
    )


def _render_block(question_analysis: QuestionAnalysis, block: AnswerContextBlock) -> str:
    lines: list[str] = []
    if block.is_attachment:
        # Label attachment content as part of its OneNote page so the model
        # synthesizes page body and attached file into one answer.
        lines.append(f"Page: {block.parent_title or block.title}")
        lines.append(f"Attached file: {block.attachment_file_name or block.title}")
    else:
        lines.append(f"Source title: {block.title}")
    lines.extend(
        [
            f"Section: {block.section_path or 'N/A'}",
            f"Heading: {block.heading or 'N/A'}",
            f"Answer type needed: {question_analysis.required_answer_type}",
            "Content:",
            block.content,
        ]
    )
    return "\n".join(lines)


def _trim_chunk_text(value: str, *, max_chars: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= max_chars:
        return cleaned

    paragraphs = _paragraphs(cleaned)
    if not paragraphs:
        return _trim_at_sentence_boundary(cleaned, max_chars=max_chars)

    selected: list[str] = []
    total_chars = 0
    for paragraph in paragraphs:
        projected = total_chars + len(paragraph) + (2 if selected else 0)
        if projected > max_chars:
            break
        selected.append(paragraph)
        total_chars = projected

    if selected:
        return "\n\n".join(selected).rstrip()

    return _trim_at_sentence_boundary(paragraphs[0], max_chars=max_chars)


def _paragraphs(value: str) -> list[str]:
    return [
        re.sub(r"[ \t]+", " ", paragraph.strip())
        for paragraph in re.split(r"\n\s*\n+", value)
        if paragraph.strip()
    ]


def _trim_at_sentence_boundary(value: str, *, max_chars: int) -> str:
    window = value[:max_chars].strip()
    sentence_match = re.search(r"^(.+[.!?])(?:\s+|$)", window, flags=re.DOTALL)
    if sentence_match and len(sentence_match.group(1)) >= max(120, max_chars // 3):
        return sentence_match.group(1).strip()
    return window.rsplit(" ", maxsplit=1)[0].rstrip() + "..."


def _first_heading(value: str) -> str | None:
    for line in value.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("#"):
            return cleaned.lstrip("#").strip() or None
        if re.match(r"^page\s*:", cleaned, flags=re.IGNORECASE):
            return re.sub(r"^page\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip() or None
    return None
