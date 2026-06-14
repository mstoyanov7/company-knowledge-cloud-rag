from __future__ import annotations

from dataclasses import dataclass
import inspect
import re
from typing import Any

from shared_schemas import ChunkDocument

from rag_api.services.query_understanding import QuestionAnalysis
from rag_api.services.retrieval_ranking import (
    chunk_relevance_breakdown,
    is_strong_semantic_match,
    subject_supports_confident_grade,
)


DIRECT_ANSWER_FOUND = "DIRECT_ANSWER_FOUND"
PARTIAL_ANSWER_FOUND = "PARTIAL_ANSWER_FOUND"
RELATED_BUT_NOT_ENOUGH = "RELATED_BUT_NOT_ENOUGH"
NO_RELEVANT_INFORMATION = "NO_RELEVANT_INFORMATION"

_RELEVANCE_ORDER = {
    "irrelevant": 0,
    "related": 1,
    "partial": 2,
    "direct": 3,
}


@dataclass(frozen=True, slots=True)
class EvidenceGrade:
    chunk_id: str
    relevance: str
    answers_question: bool
    reason: str
    confidence: float


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    sufficiency: str
    grades: tuple[EvidenceGrade, ...]
    selected_chunks: tuple[ChunkDocument, ...]


class EvidenceGrader:
    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm

    async def grade(self, question_analysis: QuestionAnalysis, chunks: list[ChunkDocument]) -> EvidenceAssessment:
        heuristic_grades = [_heuristic_grade(question_analysis, chunk) for chunk in chunks]
        grades = await self._llm_grades(question_analysis, chunks, fallback=heuristic_grades)
        guarded_grades = tuple(
            _guard_grade_with_heuristics(llm_grade, heuristic_grade)
            for llm_grade, heuristic_grade in zip(grades, heuristic_grades, strict=False)
        )
        selected = tuple(
            chunk
            for chunk, grade in zip(chunks, guarded_grades, strict=False)
            if grade.relevance == "direct" or (grade.relevance == "partial" and grade.confidence >= 0.55)
        )
        return EvidenceAssessment(
            sufficiency=_sufficiency(guarded_grades),
            grades=guarded_grades,
            selected_chunks=selected,
        )

    async def _llm_grades(
        self,
        question_analysis: QuestionAnalysis,
        chunks: list[ChunkDocument],
        *,
        fallback: list[EvidenceGrade],
    ) -> list[EvidenceGrade]:
        grader = getattr(self.llm, "grade_relevance", None)
        if grader is None or not chunks:
            return fallback

        try:
            maybe_result = grader(
                question=question_analysis.original_question,
                question_analysis=_analysis_payload(question_analysis),
                chunks=[_chunk_payload(chunk) for chunk in chunks],
            )
            payload = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result
        except Exception:
            return fallback

        parsed = _parse_llm_grade_payload(payload)
        if not parsed:
            return fallback
        fallback_by_id = {grade.chunk_id: grade for grade in fallback}
        return [parsed.get(chunk.chunk_id) or fallback_by_id[chunk.chunk_id] for chunk in chunks]


def _analysis_payload(question_analysis: QuestionAnalysis) -> dict[str, object]:
    return {
        "original_question": question_analysis.original_question,
        "detected_language": question_analysis.detected_language,
        "answer_type": question_analysis.answer_type,
        "key_entities": list(question_analysis.important_entities),
        "key_phrases": list(question_analysis.key_phrases),
        "must_have_concepts": list(question_analysis.must_have_concepts),
        "avoid_concepts": list(question_analysis.avoid_concepts),
        "expected_evidence_type": question_analysis.expected_evidence_type,
    }


def _chunk_payload(chunk: ChunkDocument) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "title": chunk.title,
        "section_path": chunk.section_path,
        "content": _trim(chunk.chunk_text, max_chars=1200),
        "score": chunk.score,
    }


def _parse_llm_grade_payload(payload: object) -> dict[str, EvidenceGrade]:
    if not isinstance(payload, dict):
        return {}
    raw_chunks = payload.get("chunks")
    if not isinstance(raw_chunks, list):
        return {}
    parsed: dict[str, EvidenceGrade] = {}
    for item in raw_chunks:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        relevance = str(item.get("relevance") or "").strip().lower()
        if not chunk_id or relevance not in _RELEVANCE_ORDER:
            continue
        confidence = _coerce_confidence(item.get("confidence"))
        answers_question = bool(item.get("answers_question")) and relevance in {"direct", "partial"}
        parsed[chunk_id] = EvidenceGrade(
            chunk_id=chunk_id,
            relevance=relevance,
            answers_question=answers_question,
            reason=_trim(str(item.get("reason") or ""), max_chars=160),
            confidence=confidence,
        )
    return parsed


def _heuristic_grade(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> EvidenceGrade:
    breakdown = chunk_relevance_breakdown(question_analysis, chunk)
    score = float(breakdown["score"])
    has_must_have = bool(breakdown["has_must_have_concept"])
    direct_signal = _direct_answer_signal(question_analysis, chunk)
    partial_signal = _partial_answer_signal(question_analysis, chunk)
    # A confident grade additionally requires the distinctive subject to be
    # declared in the page (title/section) or matched as a strong phrase, so a
    # different product's setup guide is not stamped "direct" off generic
    # scaffolding words plus a coincidental body token.
    subject_supported = subject_supports_confident_grade(question_analysis, chunk)
    # A strong vector match is itself an answer signal: the page is about the
    # question even when it shares no keywords, so it satisfies the signal gates
    # that keyword answers must pass. The cosine threshold keeps this honest.
    strong_semantic = is_strong_semantic_match(chunk)

    if subject_supported and has_must_have and (direct_signal or strong_semantic) and score >= 8.0:
        return EvidenceGrade(chunk.chunk_id, "direct", True, "matches main concept and directly answers", 0.9)
    if subject_supported and has_must_have and (partial_signal or strong_semantic) and score >= 7.0:
        return EvidenceGrade(chunk.chunk_id, "partial", True, "matches main concept with partial evidence", 0.7)
    if score > 0:
        relevance = "related" if _token_overlap(question_analysis, chunk) else "irrelevant"
        return EvidenceGrade(chunk.chunk_id, relevance, False, "related words but not sufficient evidence", 0.45)
    return EvidenceGrade(chunk.chunk_id, "irrelevant", False, "does not match the question", 0.2)


def _guard_grade_with_heuristics(llm_grade: EvidenceGrade, heuristic_grade: EvidenceGrade) -> EvidenceGrade:
    llm_rank = _RELEVANCE_ORDER[llm_grade.relevance]
    heuristic_rank = _RELEVANCE_ORDER[heuristic_grade.relevance]
    # Floor: when the deterministic heuristic is confident the chunk directly
    # answers (strong title/section/concept alignment plus an answer signal),
    # don't let a literal-minded LLM grader demote it just because the question
    # used fewer words than the page title. This keeps a partial phrasing such
    # as "how to setup flutter" consistent with the full "how to setup flutter
    # embedded hmi": both connect to the same page on logical similarity rather
    # than exact keyword coverage.
    if heuristic_grade.relevance == "direct" and heuristic_grade.answers_question and llm_rank < heuristic_rank:
        return heuristic_grade
    if llm_rank <= heuristic_rank:
        return llm_grade
    if heuristic_grade.relevance in {"irrelevant", "related"}:
        return EvidenceGrade(
            chunk_id=llm_grade.chunk_id,
            relevance=heuristic_grade.relevance,
            answers_question=False,
            reason=heuristic_grade.reason,
            confidence=min(llm_grade.confidence, heuristic_grade.confidence),
        )
    return llm_grade


def _sufficiency(grades: tuple[EvidenceGrade, ...]) -> str:
    if any(grade.relevance == "direct" and grade.answers_question for grade in grades):
        return DIRECT_ANSWER_FOUND
    if any(grade.relevance == "partial" and grade.answers_question for grade in grades):
        return PARTIAL_ANSWER_FOUND
    if any(grade.relevance == "related" for grade in grades):
        return RELATED_BUT_NOT_ENOUGH
    return NO_RELEVANT_INFORMATION


def _direct_answer_signal(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    text = " ".join([chunk.title, chunk.section_path or "", chunk.chunk_text])
    if question_analysis.answer_type == "date_or_time":
        return _specific_date_or_time_signal_present(text)
    if question_analysis.expected_evidence_type == "specific_value_or_limit":
        return _number_or_limit_signal_present(text)
    if question_analysis.answer_type == "yes_no":
        return bool(re.search(r"\b(allowed|requires?|must|cannot|approved?|denied|yes|no)\b", text, re.IGNORECASE))
    if question_analysis.answer_type == "steps":
        return bool(re.search(r"\b(step|install|configure|run|open|click|sign in|set up)\b", text, re.IGNORECASE))
    return bool(_body_text(chunk.chunk_text).strip())


def _partial_answer_signal(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    text = " ".join([chunk.title, chunk.section_path or "", chunk.chunk_text])
    if question_analysis.answer_type == "date_or_time":
        return _recurrence_signal_present(text) or _number_or_limit_signal_present(text)
    return _token_overlap(question_analysis, chunk)


def _token_overlap(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    query_tokens = _tokens(
        " ".join(
            [
                question_analysis.search_text,
                " ".join(question_analysis.key_phrases),
                " ".join(question_analysis.must_have_concepts),
            ]
        )
    )
    chunk_tokens = _tokens(" ".join([chunk.title, chunk.section_path or "", chunk.chunk_text, " ".join(chunk.tags)]))
    return bool(query_tokens.intersection(chunk_tokens))


def _specific_date_or_time_signal_present(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\b", value)
        or re.search(r"\b\d{1,2}(st|nd|rd|th)\b", value, flags=re.IGNORECASE)
        or re.search(r"\b\d{1,2}\s*[-–]?\s*[^\W_\d]{1,4}\b", value, flags=re.IGNORECASE)
        or re.search(r"\b\d{1,2}[./-]\d{1,2}([./-]\d{2,4})?\b", value)
        or re.search(
            r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December)\b",
            value,
            flags=re.IGNORECASE,
        )
    )


def _recurrence_signal_present(value: str) -> bool:
    return bool(re.search(r"\b(monthly|weekly|daily|yearly|annually|quarterly)\b", value, flags=re.IGNORECASE))


def _number_or_limit_signal_present(value: str) -> bool:
    return bool(
        re.search(r"\b\d+\b", value)
        or re.search(r"\b(up to|at least|maximum|minimum|required|requires?)\b", value, flags=re.IGNORECASE)
    )


def _body_text(value: str) -> str:
    return " ".join(line for line in value.splitlines() if not line.strip().startswith("#"))


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[^\W_]+", value) if len(token) > 2}


def _coerce_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _trim(value: str, *, max_chars: int) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars].rsplit(" ", maxsplit=1)[0].rstrip()
