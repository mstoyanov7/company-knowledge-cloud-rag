"""Detect when a specific question is ambiguous across several pages.

When retrieval finds that a specific question is equally well answered by more
than one distinct OneNote page - and no single page clearly dominates - guessing
risks answering from the wrong page. Instead we ask the user a quiz-style
follow-up listing the candidate pages so they can pick the one they mean.

The detection is fully deterministic (no LLM) for stable, repeatable behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import shorten

from shared_schemas import ChunkDocument, Clarification, ClarificationOption

from rag_api.services.evidence_grading import EvidenceGrade
from rag_api.services.query_understanding import QuestionAnalysis
from rag_api.services.retrieval_ranking import _has_must_have_concept


@dataclass(frozen=True, slots=True)
class _PageCandidate:
    source_item_id: str
    title: str
    section_path: str | None
    score: float
    hint: str


def detect_clarification(
    question_analysis: QuestionAnalysis,
    graded_chunks: list[ChunkDocument],
    grades: tuple[EvidenceGrade, ...],
    *,
    closeness_ratio: float,
    max_options: int,
) -> Clarification | None:
    """Return a clarification when several distinct pages are equally plausible.

    Returns ``None`` (let the normal answer flow run) unless every condition
    holds: the question is specific, at least two distinct pages each confidently
    answer it, and the runner-up page scores within ``closeness_ratio`` of the
    best (i.e. no single page dominates).
    """
    if not _is_specific_question(question_analysis):
        return None

    candidates = _page_candidates(question_analysis, graded_chunks, grades)
    if len(candidates) < 2:
        return None

    best, runner_up = candidates[0], candidates[1]
    if best.score <= 0:
        return None
    if runner_up.score < closeness_ratio * best.score:
        # One page clearly dominates - answer it instead of asking.
        return None

    chosen = [candidate for candidate in candidates if candidate.score >= closeness_ratio * best.score]
    chosen = chosen[: max(2, max_options)]
    options = [
        ClarificationOption(
            source_item_id=candidate.source_item_id,
            title=candidate.title,
            section_path=candidate.section_path,
            hint=candidate.hint,
        )
        for candidate in chosen
    ]
    return Clarification(
        prompt=_clarification_prompt(len(options)),
        options=options,
        original_question=question_analysis.original_question,
    )


def clarification_answer_text(clarification: Clarification) -> str:
    """Render the clarification as clean Markdown for clients without a picker."""
    lines = [clarification.prompt, ""]
    for index, option in enumerate(clarification.options, start=1):
        label = option.title
        if option.section_path:
            label = f"{label} — _{option.section_path}_"
        lines.append(f"{index}. **{label}**")
    lines.extend(["", "_Pick one above, or reply with its name._"])
    return "\n".join(lines)


def _clarification_prompt(option_count: int) -> str:
    return (
        f"I found {option_count} topics that may contain what you're looking for, "
        "but I'm not sure which one you mean. Which of these are you asking about?"
    )


def _is_specific_question(question_analysis: QuestionAnalysis) -> bool:
    # Broad/overview questions should synthesize across pages, not ask the user to
    # pick one; only pointed, single-answer questions are worth disambiguating.
    return question_analysis.specificity == "specific_fact"


def _page_candidates(
    question_analysis: QuestionAnalysis,
    graded_chunks: list[ChunkDocument],
    grades: tuple[EvidenceGrade, ...],
) -> list[_PageCandidate]:
    grade_by_id = {grade.chunk_id: grade for grade in grades}
    best_by_page: dict[str, _PageCandidate] = {}
    for chunk in graded_chunks:
        grade = grade_by_id.get(chunk.chunk_id)
        if grade is None:
            continue
        if not (grade.relevance in {"direct", "partial"} and grade.answers_question):
            continue
        if not _has_must_have_concept(question_analysis, chunk):
            continue
        # A readable attachment counts as its parent page, so page + attachment do
        # not appear as two separate topics and picking the option focuses the page.
        page_id, page_title = _page_identity(chunk)
        existing = best_by_page.get(page_id)
        if existing is not None and existing.score >= chunk.score:
            continue
        best_by_page[page_id] = _PageCandidate(
            source_item_id=page_id,
            title=page_title,
            section_path=chunk.section_path,
            score=float(chunk.score),
            hint=shorten(chunk.chunk_text.replace("\n", " ").strip(), width=140, placeholder="..."),
        )
    return sorted(best_by_page.values(), key=lambda candidate: (-candidate.score, candidate.title))


def _page_identity(chunk: ChunkDocument) -> tuple[str, str]:
    metadata = chunk.metadata or {}
    if metadata.get("document_kind") == "attachment":
        return (
            str(metadata.get("parent_source_item_id") or chunk.source_item_id),
            str(metadata.get("parent_title") or chunk.title),
        )
    return chunk.source_item_id, chunk.title
