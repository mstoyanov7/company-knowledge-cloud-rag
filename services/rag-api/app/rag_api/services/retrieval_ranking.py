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
    fuzzy_metadata_match = _fuzzy_metadata_score(question_analysis, chunk)
    direct_answer_likelihood = _answer_type_score(question_analysis, chunk)
    entity_relevance = _entity_overlap_score(question_analysis, chunk)
    weak_keyword_only_penalty = _weak_keyword_only_penalty(question_analysis, chunk)
    wrong_topic_penalty = _wrong_topic_penalty(question_analysis, chunk)
    avoid_concept_penalty = _avoid_concept_penalty(question_analysis, chunk)
    procedure_adjustment = procedure_relevance_adjustment(question_analysis, chunk)
    score = (
        semantic_similarity
        + title_relevance
        + key_phrase_match
        + fuzzy_metadata_match
        + direct_answer_likelihood
        + entity_relevance
        - weak_keyword_only_penalty
        - wrong_topic_penalty
        - avoid_concept_penalty
        + procedure_adjustment
    )
    return {
        "semantic_similarity": semantic_similarity,
        "title_relevance": title_relevance,
        "key_phrase_match": key_phrase_match,
        "fuzzy_metadata_match": fuzzy_metadata_match,
        "direct_answer_likelihood": direct_answer_likelihood,
        "entity_relevance": entity_relevance,
        "weak_keyword_only_penalty": weak_keyword_only_penalty,
        "wrong_topic_penalty": wrong_topic_penalty,
        "avoid_concept_penalty": avoid_concept_penalty,
        "procedure_adjustment": procedure_adjustment,
        "chunk_kind": chunk_kind_of(chunk),
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
    phrase_score = _key_phrase_score(question_analysis, chunk)
    fuzzy_score = _fuzzy_metadata_score(question_analysis, chunk)
    if not overlap:
        if phrase_score <= 0 and fuzzy_score <= 0:
            return 0.0

    score = 0.0
    score += len(overlap) * 1.5
    score += (len(overlap) / len(query_tokens)) * 3.0
    score += _title_relevance_score(question_analysis, chunk)
    score += len(query_tokens.intersection(heading_tokens)) * 3.0
    score += len(query_tokens.intersection(section_tokens)) * 1.0
    score += _entity_overlap_score(question_analysis, chunk)
    score += _canonical_topic_score(question_analysis, chunk)
    score += phrase_score
    score += fuzzy_score
    score += _answer_type_score(question_analysis, chunk)

    if _is_value_reference_only(question_analysis.search_text, chunk.chunk_text):
        score -= 8.0
    if _only_mentions_related_terms(question_analysis, chunk):
        score -= 4.0
    score -= _weak_keyword_only_penalty(question_analysis, chunk)
    score -= _wrong_topic_penalty(question_analysis, chunk)
    score -= _avoid_concept_penalty(question_analysis, chunk)
    score += procedure_relevance_adjustment(question_analysis, chunk)
    return max(score, 0.0)


def fuzzy_metadata_relevance_score(question: str, chunk: ChunkDocument) -> float:
    """Conservative typo tolerance over short metadata fields only.

    This is intentionally not body-text fuzzy search. It catches misspelled page,
    project, tool, and attachment names while avoiding broad accidental matches
    across long note content.
    """
    return _fuzzy_metadata_score_for_tokens(_content_tokens(question), chunk)


# Chunk kinds that hold actionable procedure content (set by the chunker).
_PROCEDURE_KINDS = {
    "procedure",
    "prerequisites",
    "install",
    "configuration",
    "commands",
    "run",
    "verification",
    "checklist",
    "troubleshooting",
}


def is_procedure_question(question_analysis: QuestionAnalysis) -> bool:
    """True for how-to/setup/install/configure/run/troubleshoot questions."""
    if question_analysis.answer_type in {"steps", "troubleshooting"}:
        return True
    return question_analysis.expected_evidence_type in {
        "procedure_or_step_lines",
        "problem_solution_or_error_resolution",
    }


def chunk_kind_of(chunk: ChunkDocument) -> str | None:
    return getattr(chunk, "chunk_kind", None) or (chunk.metadata or {}).get("chunk_kind")


def procedure_relevance_adjustment(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    """Boost procedure chunks and demote metadata-only chunks for setup/how-to
    questions so that the full procedure outranks the page metadata block."""
    if not is_procedure_question(question_analysis):
        return 0.0
    kind = chunk_kind_of(chunk)
    if kind is None:
        kind = _infer_procedure_kind(chunk.chunk_text)
    # Decisive ordering: the combined procedure chunk must outrank individual
    # sections, which must outrank overview/metadata. The metadata block repeats
    # the page title verbatim, so it needs a strong penalty to not dominate.
    if kind == "procedure":
        return 60.0
    if kind == "metadata":
        return -60.0
    if kind in {"overview", "reference"}:
        return -5.0
    if kind in _PROCEDURE_KINDS:
        return 25.0
    return 0.0


def _infer_procedure_kind(text: str) -> str | None:
    """Best-effort kind for chunks indexed before chunk_kind existed."""
    if "```" in text or re.search(r"(?m)^\s*\d+[.)]\s+\S", text):
        return "procedure"
    return None


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
    if _fuzzy_metadata_score(question_analysis, chunk) > 0:
        return 0.0
    strong_tokens = _strong_query_tokens(question_analysis)
    if overlap.intersection(strong_tokens):
        return 0.0
    return 8.0


def _wrong_topic_penalty(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    must_tokens = _concept_tokens(question_analysis.must_have_concepts)
    if not must_tokens:
        return 0.0
    haystack_tokens = _content_tokens(_chunk_haystack(chunk))
    subject_tokens = _subject_concept_tokens(question_analysis)
    subject_fuzzy_match = _has_fuzzy_metadata_token_match(subject_tokens, chunk)
    subject_missing = bool(subject_tokens) and not subject_tokens.intersection(haystack_tokens) and not subject_fuzzy_match
    # A strong key-phrase match clears the penalty - but only when the distinctive
    # subject is actually present, so fuzzy overlap on generic words cannot rescue
    # a different-topic page.
    if _key_phrase_score(question_analysis, chunk) >= 5.0 and not subject_missing:
        return 0.0
    missing_ratio = 1.0 - (len(must_tokens.intersection(haystack_tokens)) / len(must_tokens))
    if _has_fuzzy_metadata_token_match(must_tokens, chunk):
        missing_ratio = min(missing_ratio, 0.25)
    if missing_ratio <= 0 and not subject_missing:
        return 0.0
    penalty = 12.0 * missing_ratio
    if subject_missing:
        # Missing the distinctive subject of the question (e.g. a setup guide for
        # a different product) - push it well below pages that do match it.
        penalty += 14.0
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


def _subject_concept_tokens(question_analysis: QuestionAnalysis) -> set[str]:
    """The distinctive concepts a question is really about.

    Draws on the whole query signal - must-have concepts plus the planner's
    semantic/keyword expansions, key phrases, and entities - then strips generic
    how-to scaffolding (``setup``, ``project``, ``install``, ...) and weak filler
    words. This anchors "how to setup flutter project" on ``{flutter}`` while
    still letting a paraphrase like "when can I begin my day?" match a Working
    Hours page through its expansion terms (``standard``, ``working``, ...).
    Returns an empty set only when the question is entirely generic, in which
    case callers fall back to the full must-have concept set.
    """
    tokens = _content_tokens(
        " ".join(
            [
                " ".join(question_analysis.must_have_concepts),
                " ".join(question_analysis.semantic_queries),
                " ".join(question_analysis.keyword_queries),
                " ".join(question_analysis.key_phrases),
                " ".join(question_analysis.important_entities),
            ]
        )
    )
    return {token for token in tokens if token not in _GENERIC_TOPIC_TERMS and token not in _WEAK_QUERY_TERMS}


def _has_must_have_concept(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> bool:
    must_tokens = _concept_tokens(question_analysis.must_have_concepts)
    if not must_tokens:
        return True
    haystack_tokens = _content_tokens(_chunk_haystack(chunk))
    subject_tokens = _subject_concept_tokens(question_analysis)
    if subject_tokens:
        # A confident match must share the distinctive subject (e.g. "flutter"),
        # not merely a generic scaffolding word like "setup" or "project". When
        # the subject is absent, fuzzy key-phrase overlap on the generic words
        # must not rescue the chunk, so a different setup guide is never mistaken
        # for the answer.
        return bool(subject_tokens.intersection(haystack_tokens)) or _has_fuzzy_metadata_token_match(subject_tokens, chunk)
    if must_tokens.intersection(haystack_tokens):
        return True
    return _key_phrase_score(question_analysis, chunk) >= 5.0 or _has_fuzzy_metadata_token_match(must_tokens, chunk)


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
    in_fence = False
    code: list[str] = []
    for line in value.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("```"):
            code.append(line)
            if in_fence:
                segments.append(("\n".join(code), False))
                code = []
            in_fence = not in_fence
            continue
        if in_fence:
            code.append(line)
            continue
        for raw_segment in re.split(r"(?<=[.!?])\s+", line):
            cleaned = raw_segment.strip(" \t\r\n-*")
            if not cleaned:
                continue
            is_page_heading = bool(re.match(r"^page\s*:", cleaned, flags=re.IGNORECASE))
            is_heading = cleaned.startswith("#") or is_page_heading
            segments.append((cleaned, is_heading))
    if code:
        segments.append(("\n".join(code), False))
    return segments


def _heading_text(value: str) -> str:
    return " ".join(segment for segment, is_heading in _split_content_segments(value) if is_heading)


def _body_text_without_headings(value: str) -> str:
    return " ".join(segment for segment, is_heading in _split_content_segments(value) if not is_heading)


def _fuzzy_metadata_score(question_analysis: QuestionAnalysis, chunk: ChunkDocument) -> float:
    return _fuzzy_metadata_score_for_tokens(_analysis_tokens(question_analysis), chunk)


def _fuzzy_metadata_score_for_tokens(query_tokens: set[str], chunk: ChunkDocument) -> float:
    meaningful_query_tokens = _meaningful_fuzzy_tokens(query_tokens)
    if not meaningful_query_tokens:
        return 0.0

    title_tokens = _meaningful_fuzzy_tokens(_content_tokens(chunk.title))
    section_tokens = _meaningful_fuzzy_tokens(_content_tokens(chunk.section_path or ""))
    heading_tokens = _meaningful_fuzzy_tokens(_content_tokens(_heading_text(chunk.chunk_text)))
    tag_tokens = _meaningful_fuzzy_tokens(_content_tokens(" ".join(chunk.tags)))
    metadata_tokens = _meaningful_fuzzy_tokens(_metadata_name_tokens(chunk))

    weighted_sources: tuple[tuple[set[str], float], ...] = (
        (title_tokens | metadata_tokens, 9.0),
        (section_tokens | heading_tokens, 6.0),
        (tag_tokens, 4.0),
    )

    matched_query_tokens: set[str] = set()
    score = 0.0
    for query_token in meaningful_query_tokens:
        best = 0.0
        for candidate_tokens, weight in weighted_sources:
            for candidate_token in candidate_tokens:
                if query_token == candidate_token:
                    continue
                similarity = _near_token_similarity(query_token, candidate_token)
                if similarity <= 0:
                    continue
                best = max(best, weight * similarity)
        if best > 0:
            matched_query_tokens.add(query_token)
            score += best

    if not matched_query_tokens:
        return 0.0
    coverage = len(matched_query_tokens) / len(meaningful_query_tokens)
    return score + (coverage * 3.0)


def _has_fuzzy_metadata_token_match(query_tokens: set[str], chunk: ChunkDocument) -> bool:
    return _fuzzy_metadata_score_for_tokens(query_tokens, chunk) > 0


def _metadata_name_tokens(chunk: ChunkDocument) -> set[str]:
    metadata = chunk.metadata or {}
    values = [
        str(metadata.get(key) or "")
        for key in (
            "title",
            "file_name",
            "attachment_file_name",
            "parent_title",
            "section_name",
            "notebook_name",
            "source_title",
            "page_title",
        )
    ]
    return _content_tokens(" ".join(values))


def _meaningful_fuzzy_tokens(tokens: set[str]) -> set[str]:
    return {
        token
        for token in tokens
        if len(token) >= 5 and token not in _GENERIC_TOPIC_TERMS and token not in _WEAK_QUERY_TERMS
    }


def _near_token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    max_len = max(len(left), len(right))
    min_len = min(len(left), len(right))
    if min_len < 5:
        return 0.0
    if abs(len(left) - len(right)) > 2:
        return 0.0
    max_distance = 1 if max_len <= 8 else 2
    distance = _bounded_edit_distance(left, right, max_distance)
    if distance > max_distance:
        return 0.0
    similarity = 1.0 - (distance / max_len)
    return similarity if similarity >= 0.78 else 0.0


def _bounded_edit_distance(left: str, right: str, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            insert = current[right_index - 1] + 1
            delete = previous[right_index] + 1
            replace = previous[right_index - 1] + (0 if left_char == right_char else 1)
            value = min(insert, delete, replace)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


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


# Generic "how-to scaffolding" words that appear across many setup/guide pages
# and therefore do not, on their own, identify which page a question is about.
# Stored in normalized form so they line up with ``_content_tokens`` output.
_GENERIC_TOPIC_TERMS = {
    _normalize_token(term)
    for term in (
        "setup",
        "install",
        "installation",
        "configure",
        "configuration",
        "config",
        "guide",
        "tutorial",
        "step",
        "steps",
        "process",
        "procedure",
        "instruction",
        "instructions",
        "documentation",
        "overview",
        "project",
        "projects",
        "create",
        "build",
        "run",
        "enable",
        "usage",
        "manual",
        "reference",
    )
}

# Weak filler words that are too common to identify a topic on their own. Kept
# out of the distinctive-subject set so a coincidental shared word (e.g. "paid"
# between a salary question and a leave note) is not treated as the subject.
_WEAK_QUERY_TERMS = {
    _normalize_token(term)
    for term in (
        "date",
        "day",
        "detail",
        "details",
        "info",
        "information",
        "note",
        "notes",
        "paid",
        "policy",
        "question",
        "rule",
        "rules",
        "time",
    )
}
