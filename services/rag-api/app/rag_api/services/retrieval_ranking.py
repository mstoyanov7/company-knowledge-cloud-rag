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


def chunk_relevance_breakdown(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> dict[str, float | bool]:
    semantic_similarity = float(chunk.score)
    title_relevance = _title_relevance_score(question_analysis, chunk)
    key_phrase_match = _key_phrase_score(question_analysis, chunk)
    direct_answer_likelihood = _answer_type_score(question_analysis, chunk)
    entity_relevance = _entity_overlap_score(question_analysis, chunk)
    weak_keyword_only_penalty = _weak_keyword_only_penalty(question_analysis, chunk)
    wrong_topic_penalty = _wrong_topic_penalty(question_analysis, chunk)
    avoid_concept_penalty = _avoid_concept_penalty(question_analysis, chunk)
    score = (
        semantic_similarity
        + title_relevance
        + key_phrase_match
        + direct_answer_likelihood
        + entity_relevance
        - weak_keyword_only_penalty
        - wrong_topic_penalty
        - avoid_concept_penalty
    )
    return {
        "semantic_similarity": semantic_similarity,
        "title_relevance": title_relevance,
        "key_phrase_match": key_phrase_match,
        "direct_answer_likelihood": direct_answer_likelihood,
        "entity_relevance": entity_relevance,
        "weak_keyword_only_penalty": weak_keyword_only_penalty,
        "wrong_topic_penalty": wrong_topic_penalty,
        "avoid_concept_penalty": avoid_concept_penalty,
        "score": max(score, 0.0),
        "has_must_have_concept": _has_must_have_concept(question_analysis, chunk),
    }


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
        phrase_score = _key_phrase_score(question_analysis, chunk)
        if phrase_score <= 0:
            return 0.0

    score = 0.0
    score += len(overlap) * 1.5
    score += (len(overlap) / len(query_tokens)) * 3.0
    score += _title_relevance_score(question_analysis, chunk)
    score += len(query_tokens.intersection(heading_tokens)) * 3.0
    score += len(query_tokens.intersection(section_tokens)) * 1.0
    score += _entity_overlap_score(question_analysis, chunk)
    score += _canonical_topic_score(question_analysis, chunk)
    score += _key_phrase_score(question_analysis, chunk)
    score += _answer_type_score(question_analysis, chunk)

    if _is_value_reference_only(question_analysis.search_text, chunk.chunk_text):
        score -= 8.0
    if _only_mentions_related_terms(question_analysis, chunk):
        score -= 4.0
    score -= _weak_keyword_only_penalty(question_analysis, chunk)
    score -= _wrong_topic_penalty(question_analysis, chunk)
    score -= _avoid_concept_penalty(question_analysis, chunk)
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


def _title_relevance_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    query_tokens = _analysis_tokens(question_analysis)
    title_tokens = _content_tokens(" ".join([chunk.title, chunk.section_path or "", _heading_text(chunk.chunk_text)]))
    overlap = query_tokens.intersection(title_tokens)
    score = len(overlap) * 4.0
    must_tokens = _concept_tokens(question_analysis.must_have_concepts)
    if must_tokens:
        score += len(must_tokens.intersection(title_tokens)) * 5.0
    return score


def _key_phrase_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    haystack = _chunk_haystack(chunk)
    title_haystack = _normalized_words(" ".join([chunk.title, chunk.section_path or "", _heading_text(chunk.chunk_text)]))
    score = 0.0
    for phrase in _question_phrases(question_analysis):
        normalized_phrase = _normalized_words(phrase)
        if not normalized_phrase or len(normalized_phrase.split()) < 2:
            continue
        if normalized_phrase in title_haystack:
            score += 14.0
        elif normalized_phrase in haystack:
            score += 7.0
        else:
            phrase_tokens = set(normalized_phrase.split())
            title_tokens = _content_tokens(title_haystack)
            body_tokens = _content_tokens(haystack)
            if phrase_tokens and phrase_tokens.issubset(title_tokens | body_tokens):
                score += 5.0
            elif phrase_tokens:
                title_overlap = phrase_tokens.intersection(title_tokens)
                all_overlap = phrase_tokens.intersection(title_tokens | body_tokens)
                if len(title_overlap) >= min(2, len(phrase_tokens)):
                    score += 6.0
                elif len(all_overlap) >= 2 and len(all_overlap) / len(phrase_tokens) >= 0.6:
                    score += 4.0
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
    if answer_type == "date_or_time" and _date_or_time_signal_present(text):
        score += 8.0
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


def _weak_keyword_only_penalty(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    query_tokens = _analysis_tokens(question_analysis)
    if not query_tokens:
        return 0.0
    haystack_tokens = _content_tokens(_chunk_haystack(chunk))
    overlap = query_tokens.intersection(haystack_tokens)
    if not overlap:
        return 0.0
    if _has_must_have_concept(question_analysis, chunk):
        return 0.0
    if _key_phrase_score(question_analysis, chunk) >= 5.0:
        return 0.0
    strong_tokens = _strong_query_tokens(question_analysis)
    if overlap.intersection(strong_tokens):
        return 0.0
    return 8.0


def _wrong_topic_penalty(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    must_tokens = _concept_tokens(question_analysis.must_have_concepts)
    if not must_tokens:
        return 0.0
    if _key_phrase_score(question_analysis, chunk) >= 5.0:
        return 0.0
    haystack_tokens = _content_tokens(_chunk_haystack(chunk))
    missing_ratio = 1.0 - (len(must_tokens.intersection(haystack_tokens)) / len(must_tokens))
    if missing_ratio <= 0:
        return 0.0
    penalty = 12.0 * missing_ratio
    if _answer_type_score(question_analysis, chunk) <= 0:
        penalty += 4.0
    return penalty


def _avoid_concept_penalty(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    avoid_tokens = _concept_tokens(question_analysis.avoid_concepts)
    if not avoid_tokens:
        return 0.0
    title_tokens = _content_tokens(" ".join([chunk.title, chunk.section_path or "", _heading_text(chunk.chunk_text)]))
    body_tokens = _content_tokens(_body_text_without_headings(chunk.chunk_text))
    return (len(avoid_tokens.intersection(title_tokens)) * 8.0) + (
        len(avoid_tokens.intersection(body_tokens)) * 3.0
    )


def _has_must_have_concept(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    must_tokens = _concept_tokens(question_analysis.must_have_concepts)
    if not must_tokens:
        return True
    haystack_tokens = _content_tokens(_chunk_haystack(chunk))
    if must_tokens.intersection(haystack_tokens):
        return True
    return _key_phrase_score(question_analysis, chunk) >= 5.0


def _strong_query_tokens(question_analysis: QuestionAnalysis) -> set[str]:
    tokens = _concept_tokens(question_analysis.must_have_concepts)
    for phrase in _question_phrases(question_analysis):
        phrase_tokens = _content_tokens(phrase)
        if len(phrase_tokens) > 1:
            tokens.update(phrase_tokens)
    return tokens


def _question_phrases(question_analysis: QuestionAnalysis) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            [
                *question_analysis.key_phrases,
                *question_analysis.semantic_queries,
                *question_analysis.keyword_queries,
            ]
        )
    )


def _concept_tokens(values: tuple[str, ...]) -> set[str]:
    return _content_tokens(" ".join(values))


def _chunk_haystack(chunk: ChunkDocument) -> str:
    return _normalized_words(
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


def _date_or_time_signal_present(value: str) -> bool:
    return bool(
        _value_signal_present(value)
        or re.search(r"\b\d{1,2}(st|nd|rd|th)\b", value, flags=re.IGNORECASE)
        or re.search(r"\b\d{1,2}\s*[-–]?\s*[^\W_\d]{1,4}\b", value, flags=re.IGNORECASE)
        or re.search(r"\b(monthly|weekly|daily|yearly|annually|quarterly)\b", value, flags=re.IGNORECASE)
        or re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
            value,
            flags=re.IGNORECASE,
        )
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
        for token in re.findall(r"[^\W_]+", value.lower())
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
    return " ".join(_normalize_token(token) for token in re.findall(r"[^\W_]+", value.lower()))
