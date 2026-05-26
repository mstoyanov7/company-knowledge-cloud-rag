from __future__ import annotations

import re

from shared_schemas import ChunkDocument

from rag_api.services.query_understanding import QuestionAnalysis, canonical_key_phrase


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def rank_chunks_by_question_analysis(
    question_analysis: QuestionAnalysis,
    chunks: list[ChunkDocument],
    *,
    top_k: int,
) -> list[ChunkDocument]:
    ranked: list[tuple[float, ChunkDocument]] = []
    for chunk in chunks:
        score = chunk.score + analysis_relevance_score(question_analysis, chunk)
        if score <= 0:
            continue
        ranked.append((score, chunk.model_copy(update={"score": score})))
    ranked.sort(key=lambda item: (-item[0], item[1].title, item[1].chunk_index))
    return [chunk for _score, chunk in ranked[:top_k]]


def analysis_relevance_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    query_tokens = _analysis_tokens(question_analysis)
    if not query_tokens:
        return 0.0

    title_tokens = _content_tokens(chunk.title)
    section_tokens = _content_tokens(chunk.section_path or "")
    body_tokens = _content_tokens(chunk.chunk_text)
    tag_tokens = _content_tokens(" ".join(chunk.tags))
    heading_tokens = _content_tokens(_heading_text(chunk.chunk_text))
    all_tokens = title_tokens | section_tokens | body_tokens | tag_tokens | heading_tokens
    overlap = query_tokens.intersection(all_tokens)
    if not overlap:
        return 0.0

    score = 0.0
    score += len(overlap) * 1.5
    score += (len(overlap) / len(query_tokens)) * 3.0
    score += len(query_tokens.intersection(title_tokens)) * 4.0
    score += len(query_tokens.intersection(heading_tokens)) * 3.0
    score += len(query_tokens.intersection(section_tokens)) * 1.0
    score += _entity_overlap_score(question_analysis, chunk)
    score += _canonical_topic_score(question_analysis, chunk)
    score += _answer_type_score(question_analysis, chunk)

    if _is_value_reference_only(question_analysis.search_text, chunk.chunk_text):
        score -= 8.0
    if _only_mentions_related_terms(question_analysis, chunk):
        score -= 4.0
    return max(score, 0.0)


def _analysis_tokens(question_analysis: QuestionAnalysis) -> set[str]:
    values = [
        question_analysis.original_question,
        question_analysis.search_text,
        " ".join(question_analysis.important_entities),
        " ".join(question_analysis.synonyms),
        " ".join(question_analysis.paraphrases),
    ]
    return _content_tokens(" ".join(values))


def _entity_overlap_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    haystack = _normalized_words(
        " ".join(
            [
                chunk.title,
                chunk.section_path or "",
                _heading_text(chunk.chunk_text),
                chunk.chunk_text,
                " ".join(chunk.tags),
            ]
        )
    )
    score = 0.0
    for entity in question_analysis.important_entities:
        normalized_entity = _normalized_words(entity)
        if not normalized_entity:
            continue
        if normalized_entity in haystack:
            score += 5.0
    return score


def _canonical_topic_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    phrase = canonical_key_phrase(question_analysis.search_text)
    if not phrase:
        return 0.0
    title_and_headings = _normalized_words(" ".join([chunk.title, chunk.section_path or "", _heading_text(chunk.chunk_text)]))
    body = _normalized_words(chunk.chunk_text)
    score = 0.0
    if phrase in title_and_headings:
        score += 12.0
    elif phrase in body:
        score += 4.0
    return score


def _answer_type_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    text = chunk.chunk_text
    answer_type = question_analysis.required_answer_type
    score = 0.0
    if answer_type == "yes_no" and re.search(r"\b(allowed|requires?|must|can|cannot|approved?)\b", text, re.IGNORECASE):
        score += 5.0
    if answer_type == "steps" and re.search(r"\b(step|install|configure|run|open|click|sign in|set up)\b", text, re.IGNORECASE):
        score += 5.0
    if answer_type in {"definition", "explanation", "summary"} and (
        ":" in text or re.search(r"\b(goal|objective|purpose|focus|is|means|refers)\b", text, re.IGNORECASE)
    ):
        score += 3.0
    if question_analysis.specificity == "specific_fact" and _value_signal_present(text):
        score += 3.0
    if question_analysis.specificity == "broad_explanation" and len(_split_content_segments(text)) >= 2:
        score += 2.0
    return score


def _only_mentions_related_terms(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    title_tokens = _content_tokens(chunk.title)
    heading_tokens = _content_tokens(_heading_text(chunk.chunk_text))
    body_tokens = _content_tokens(_body_text_without_headings(chunk.chunk_text))
    query_tokens = _analysis_tokens(question_analysis)
    body_overlap = query_tokens.intersection(body_tokens)
    strong_overlap = query_tokens.intersection(title_tokens | heading_tokens)
    if strong_overlap:
        return False
    if question_analysis.required_answer_type in {"yes_no", "specific_fact"} and not _value_signal_present(chunk.chunk_text):
        return len(body_overlap) <= 1
    return False


def _is_value_reference_only(question: str, value: str) -> bool:
    if not _is_value_question(question):
        return False
    key_phrase = canonical_key_phrase(question)
    if not key_phrase or key_phrase not in _normalized_words(value):
        return False
    return not _value_signal_present(value)


def _is_value_question(question: str) -> bool:
    normalized = _normalized_words(question)
    return bool(
        "work hour" in normalized
        or "office hour" in normalized
        or "what time" in normalized
        or "what hour" in normalized
        or re.search(r"\b(when|how many|how much)\b", normalized)
    )


def _value_signal_present(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\b", value)
        or re.search(r"\b\d+\s*(hours?|days?|minutes?)\b", value, flags=re.IGNORECASE)
        or re.search(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", value, flags=re.IGNORECASE)
    )


def _split_content_segments(value: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    for raw_segment in re.split(r"(?<=[.!?])\s+|\n+", value):
        cleaned = raw_segment.strip(" \t\r\n-*")
        if not cleaned:
            continue
        is_page_heading = bool(re.match(r"^page\s*:", cleaned, flags=re.IGNORECASE))
        is_heading = cleaned.startswith("#") or is_page_heading
        segments.append((cleaned, is_heading))
    return segments


def _heading_text(value: str) -> str:
    return " ".join(segment for segment, is_heading in _split_content_segments(value) if is_heading)


def _body_text_without_headings(value: str) -> str:
    return " ".join(segment for segment, is_heading in _split_content_segments(value) if not is_heading)


def _content_tokens(value: str) -> set[str]:
    return {
        _normalize_token(token)
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _normalize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _normalized_words(value: str) -> str:
    return " ".join(_normalize_token(token) for token in re.findall(r"[a-z0-9]+", value.lower()))
