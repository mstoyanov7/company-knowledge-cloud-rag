from __future__ import annotations

from dataclasses import dataclass

from shared_schemas import ChunkDocument, Citation

from rag_api.services.query_understanding import QuestionAnalysis


@dataclass(frozen=True, slots=True)
class AnswerContextBlock:
    citation_index: int
    title: str
    section_path: str | None
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
    max_chars: int = 6000,
) -> AnswerContext:
    blocks: list[AnswerContextBlock] = []
    rendered_blocks: list[str] = []
    total_chars = 0

    for chunk, citation in zip(retrieved_chunks, citations, strict=False):
        content = _trim_chunk_text(chunk.chunk_text, max_chars=max(800, min(1800, max_chars // 2)))
        block = AnswerContextBlock(
            citation_index=citation.index,
            title=chunk.title,
            section_path=chunk.section_path,
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
            f"Answer type needed: {question_analysis.required_answer_type}",
            "Content:",
            block.content,
        ]
    )


def _trim_chunk_text(value: str, *, max_chars: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", maxsplit=1)[0].rstrip() + "..."
