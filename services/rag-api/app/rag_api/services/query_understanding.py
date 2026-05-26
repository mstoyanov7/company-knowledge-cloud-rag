from __future__ import annotations

from dataclasses import dataclass
import inspect
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class QuestionAnalysis:
    original_question: str
    detected_language: str
    answer_type: str
    important_entities: tuple[str, ...]
    key_phrases: tuple[str, ...]
    rewritten_question: str
    semantic_queries: tuple[str, ...]
    keyword_queries: tuple[str, ...]
    must_have_concepts: tuple[str, ...]
    avoid_concepts: tuple[str, ...]
    expected_evidence_type: str
    specificity: str

    @property
    def main_intent(self) -> str | None:
        return None

    @property
    def intent(self) -> str | None:
        return self.main_intent

    @property
    def required_answer_type(self) -> str:
        return self.answer_type

    @property
    def synonyms(self) -> tuple[str, ...]:
        return self.semantic_queries

    @property
    def paraphrases(self) -> tuple[str, ...]:
        return self.semantic_queries

    @property
    def expansions(self) -> tuple[str, ...]:
        return self.semantic_queries

    @property
    def key_entities(self) -> tuple[str, ...]:
        return self.important_entities

    @property
    def search_queries(self) -> tuple[str, ...]:
        return tuple(
            _dedupe_preserving_order(
                [
                    self.original_question,
                    self.rewritten_question,
                    *self.key_phrases,
                    *self.keyword_queries,
                    *self.semantic_queries,
                ]
            )
        )

    @property
    def search_text(self) -> str:
        return " ".join(self.search_queries).strip()


QueryUnderstanding = QuestionAnalysis


class QueryPlanner:
    def __init__(self, llm: object | None = None) -> None:
        self.llm = llm

    async def plan(self, question: str) -> QuestionAnalysis:
        base = analyze_question(question)
        planner = getattr(self.llm, "plan_queries", None)
        if planner is None:
            return base

        try:
            maybe_result = planner(
                question=question,
                detected_language=base.detected_language,
                answer_type=base.answer_type,
                important_entities=list(base.important_entities),
                key_phrases=list(base.key_phrases),
                keyword_queries=list(base.keyword_queries),
                must_have_concepts=list(base.must_have_concepts),
                avoid_concepts=list(base.avoid_concepts),
                expected_evidence_type=base.expected_evidence_type,
            )
            payload = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result
        except Exception:
            return base

        if not isinstance(payload, dict):
            return base
        return _merge_llm_plan(base, payload)


_QUESTION_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(how\s+do|how\s+can|steps?|procedure|process|setup|configure|install)\b", "steps"),
    (r"\b(compare|difference|versus|vs\.?)\b", "comparison"),
    (r"\b(when|what\s+(date|day|time)|on\s+what\s+(date|day)|which\s+(date|day)|at\s+what\s+time)\b", "date_or_time"),
    (r"\b(is|are)\s+there\s+(any\s+)?(info|information|details?|notes?|anything)\b", "specific_fact"),
    (r"\b(why|explain|describe|details|tell\s+me\s+about)\b", "explanation"),
    (r"\b(summary|summarize|overview|main\s+points)\b", "summary"),
    (r"\b(error|issue|problem|troubleshoot|fix|fail|broken)\b", "troubleshooting"),
    (r"\b(can|could|allowed|possible|permit|permission|should)\b", "yes_no"),
    (r"\b(list|which|what\s+are)\b", "list"),
    (r"\b(what\s+is|what\s+was|define|meaning)\b", "definition"),
)

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "about",
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
    "info",
    "information",
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
    "there",
    "to",
    "was",
    "what",
    "whate",
    "whats",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

_WEAK_SINGLE_QUERY_TERMS = {
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
}


def analyze_question(question: str) -> QuestionAnalysis:
    normalized_question = _normalized_words(question)
    detected_language = _detect_language(question)
    answer_type = _required_answer_type(normalized_question)
    specificity = _specificity(normalized_question, answer_type)
    key_phrases = tuple(_extract_key_phrases(question))
    entities = tuple(_extract_entities(question, key_phrases))
    must_have_concepts = tuple(_must_have_concepts(question, key_phrases))
    keyword_queries = tuple(_keyword_queries(question, entities, key_phrases))
    rewritten_question = _rewrite_question(question, entities, answer_type)
    expected_evidence_type = _expected_evidence_type(answer_type, normalized_question)

    return QuestionAnalysis(
        original_question=question,
        detected_language=detected_language,
        answer_type=answer_type,
        important_entities=entities,
        key_phrases=key_phrases,
        rewritten_question=rewritten_question,
        semantic_queries=(),
        keyword_queries=keyword_queries,
        must_have_concepts=must_have_concepts,
        avoid_concepts=(),
        expected_evidence_type=expected_evidence_type,
        specificity=specificity,
    )


def understand_query(question: str) -> QuestionAnalysis:
    return analyze_question(question)


def canonical_key_phrase(value: str) -> str:
    tokens = _content_tokens_ordered(value)
    if len(tokens) < 2:
        return ""
    best_phrase = ""
    best_count = 1
    best_size = 0
    for size in range(4, 1, -1):
        counts: dict[str, int] = {}
        for index in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[index : index + size])
            counts[phrase] = counts.get(phrase, 0) + 1
        for phrase, count in counts.items():
            if count > best_count or (count > 1 and count == best_count and size > best_size):
                best_phrase = phrase
                best_count = count
                best_size = size
    if best_phrase:
        return best_phrase
    return " ".join(tokens[: min(3, len(tokens))])


def _merge_llm_plan(base: QuestionAnalysis, payload: dict[str, Any]) -> QuestionAnalysis:
    important_entities = tuple(
        _dedupe_preserving_order(
            [
                *base.important_entities,
                *_coerce_string_list(payload.get("key_entities")),
                *_coerce_string_list(payload.get("important_entities")),
            ]
        )
    )
    key_phrases = tuple(
        _dedupe_preserving_order(
            [
                *base.key_phrases,
                *_coerce_string_list(payload.get("key_phrases")),
            ]
        )[:8]
    )
    rewritten_question = _coerce_string(payload.get("rewritten_question")) or base.rewritten_question
    semantic_queries = tuple(
        _filter_query_list(
            _coerce_string_list(payload.get("semantic_queries")),
            key_phrases=key_phrases,
        )[:5]
    )
    keyword_queries = tuple(
        _filter_query_list(
            _dedupe_preserving_order(
                [
                    *_coerce_string_list(payload.get("keyword_queries")),
                    *base.keyword_queries,
                ]
            ),
            key_phrases=key_phrases,
        )[:5]
    )
    answer_type = _coerce_string(payload.get("answer_type")) or base.answer_type
    expected_evidence_type = _coerce_string(payload.get("expected_evidence_type")) or base.expected_evidence_type
    must_have_concepts = tuple(
        _dedupe_preserving_order(
            [
                *base.must_have_concepts,
                *_coerce_string_list(payload.get("must_have_concepts")),
            ]
        )[:8]
    )
    avoid_concepts = tuple(_dedupe_preserving_order(_coerce_string_list(payload.get("avoid_concepts")))[:8])

    return QuestionAnalysis(
        original_question=base.original_question,
        detected_language=_coerce_string(payload.get("detected_language")) or base.detected_language,
        answer_type=answer_type,
        important_entities=important_entities,
        key_phrases=key_phrases,
        rewritten_question=rewritten_question,
        semantic_queries=semantic_queries,
        keyword_queries=keyword_queries,
        must_have_concepts=must_have_concepts,
        avoid_concepts=avoid_concepts,
        expected_evidence_type=expected_evidence_type,
        specificity=_specificity(_normalized_words(base.original_question), answer_type),
    )


def _detect_language(question: str) -> str:
    if re.search(r"[\u0400-\u04ff]", question):
        return "bg"
    return "en"


def _required_answer_type(normalized_question: str) -> str:
    for pattern, answer_type in _QUESTION_TYPE_PATTERNS:
        if re.search(pattern, normalized_question):
            return answer_type
    return "specific_fact" if re.search(r"\b(when|where|who|how\s+many|how\s+much)\b", normalized_question) else "explanation"


def _specificity(normalized_question: str, answer_type: str) -> str:
    if answer_type in {"summary", "explanation", "comparison", "list"}:
        return "broad_explanation"
    if re.search(r"\b(main|overall|overview|summarize|explain)\b", normalized_question):
        return "broad_explanation"
    return "specific_fact"


def _expected_evidence_type(answer_type: str, normalized_question: str) -> str:
    if answer_type == "date_or_time":
        return "date_or_time_value"
    if answer_type == "steps":
        return "procedure_or_step_lines"
    if answer_type == "comparison":
        return "contrasting_facts"
    if answer_type == "yes_no":
        return "policy_or_permission_statement"
    if answer_type == "specific_fact" and re.search(r"\b(when|how many|how much|number)\b", normalized_question):
        return "specific_value_or_limit"
    if answer_type == "troubleshooting":
        return "problem_solution_or_error_resolution"
    return "direct_text_evidence"


def _extract_entities(question: str, key_phrases: tuple[str, ...]) -> list[str]:
    entities: list[str] = []
    entities.extend(re.findall(r"['\"]([^'\"]{2,80})['\"]", question))
    entities.extend(
        match
        for match in re.findall(r"\b[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,4}\b", question)
        if _normalized_words(match) not in _STOP_WORDS
    )
    entities.extend(key_phrases)
    entities.extend(_content_tokens_ordered(question))
    return _dedupe_preserving_order(entities)


def _extract_key_phrases(question: str) -> list[str]:
    tokens = _content_tokens_ordered(question)
    phrases: list[str] = []
    for size in range(min(4, len(tokens)), 1, -1):
        for index in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[index : index + size])
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases[:8]


def _must_have_concepts(question: str, key_phrases: tuple[str, ...]) -> list[str]:
    phrase_tokens: list[str] = []
    for phrase in key_phrases:
        phrase_tokens.extend(_content_tokens_ordered(phrase))
    tokens = phrase_tokens or _content_tokens_ordered(question)
    return _dedupe_preserving_order([token for token in tokens if token not in _WEAK_SINGLE_QUERY_TERMS])[:8]


def _keyword_queries(question: str, entities: tuple[str, ...], key_phrases: tuple[str, ...]) -> list[str]:
    tokens = _content_tokens_ordered(question)
    queries = []
    queries.extend(key_phrases[:3])
    if entities:
        queries.append(" ".join(entities[:8]))
    if tokens:
        queries.append(" ".join(tokens[:10]))
    return _filter_query_list(_dedupe_preserving_order(queries), key_phrases=key_phrases)


def _rewrite_question(question: str, entities: tuple[str, ...], answer_type: str) -> str:
    entity_text = " ".join(entities[:8])
    if not entity_text:
        return question
    return f"{answer_type.replace('_', ' ')} answer about {entity_text}"


def _content_tokens_ordered(value: str) -> list[str]:
    return [
        _normalize_token(token)
        for token in re.findall(r"[^\W_]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    ]


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


def _filter_query_list(values: list[str], *, key_phrases: tuple[str, ...]) -> list[str]:
    filtered: list[str] = []
    normalized_phrases = {_normalized_words(phrase) for phrase in key_phrases if len(_content_tokens_ordered(phrase)) > 1}
    for value in _dedupe_preserving_order(values):
        tokens = _content_tokens_ordered(value)
        if not tokens:
            continue
        normalized_value = _normalized_words(value)
        if len(tokens) == 1 and tokens[0] in _WEAK_SINGLE_QUERY_TERMS and normalized_value not in normalized_phrases:
            continue
        filtered.append(value)
    return filtered


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(value).strip())
    return deduped


def _coerce_string(value: object) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []
