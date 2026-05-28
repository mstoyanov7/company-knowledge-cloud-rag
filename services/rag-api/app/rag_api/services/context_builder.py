from __future__ import annotations

from dataclasses import dataclass
import re

from shared_schemas import ChunkDocument, Citation

from rag_api.services.query_understanding import QuestionAnalysis


@dataclass(frozen=True, slots=True)
class AnswerContextBlock:
    citation_index: int
    title: str
    section_path: str | None
    heading: str | None
    content: str
    source_url: str


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

    for chunk, citation in zip(retrieved_chunks, citations, strict=False):
        content = _trim_chunk_text(chunk.chunk_text, max_chars=max(400, min(2800, max_chars // 2)))
        block = AnswerContextBlock(
            citation_index=citation.index,
            title=chunk.title,
            section_path=chunk.section_path,
            heading=_first_heading(chunk.chunk_text),
            content=content,
            source_url=chunk.source_url,
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
    return "\n".join(
        [
            f"Source title: {block.title}",
            f"Section: {block.section_path or 'N/A'}",
            f"Heading: {block.heading or 'N/A'}",
            f"Answer type needed: {question_analysis.required_answer_type}",
            "Content:",
            block.content,
        ]
    )


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
