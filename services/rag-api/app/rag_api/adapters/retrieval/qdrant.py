from __future__ import annotations

import time
from datetime import datetime
import re
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from shared_schemas import (
    AccessScope,
    AclBinding,
    AppSettings,
    ChunkDocument,
    RetrievalMetadata,
    RetrievalRequest,
    RetrievalResult,
)

from shared_schemas.embeddings import Embedder

from rag_api.adapters.embeddings import build_query_embedder
from rag_api.services.query_understanding import canonical_key_phrase
from rag_api.services.retrieval_ranking import fuzzy_metadata_relevance_score

# Per-scroll batch size and the absolute safety cap used when the lexical scan
# limit is configured as "unbounded" (<= 0).
_LEXICAL_SCAN_BATCH = 512
_LEXICAL_SCAN_HARD_CAP = 100_000


class QdrantAclRetriever:
    name = "qdrant-hybrid-acl"

    def __init__(self, settings: AppSettings, *, embedder: Embedder | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or build_query_embedder(settings)
        self.client = QdrantClient(url=settings.qdrant_url)

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        if request.access_scope is None:
            raise ValueError("ACL-aware retrieval requires an access scope.")

        access_scope = request.access_scope
        collections = self._collections_for_request(request)
        payload_filter = self.build_payload_filter(
            access_scope,
            section_filters=request.section_filters,
            focus_source_item_ids=request.focus_source_item_ids,
        )
        query_vector = self.embedder.embed_query(request.question)
        candidates: list[ChunkDocument] = []
        collections_queried: list[str] = []

        for collection_name in collections:
            collection_was_queried = False
            try:
                response = self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    query_filter=payload_filter,
                    limit=request.top_k,
                    with_payload=True,
                    with_vectors=False,
                    score_threshold=self.settings.retrieval_score_threshold,
                )
            except (UnexpectedResponse, ValueError):
                response = None

            if response is not None:
                collection_was_queried = True
                for point in response.points:
                    if point.payload:
                        cosine = float(point.score or 0.0)
                        chunk = self._chunk_from_payload(point.payload, score=cosine)
                        # Carry the raw cosine so the downstream pipeline can treat a
                        # strong semantic match as topical evidence even without shared
                        # keywords (gated by RETRIEVAL_SEMANTIC_CONFIDENT_SCORE).
                        chunk = chunk.model_copy(
                            update={"metadata": {**(chunk.metadata or {}), "semantic_score": cosine}}
                        )
                        candidates.append(chunk)

            lexical_candidates = self._lexical_candidates(collection_name, payload_filter, request.question)
            if lexical_candidates:
                collection_was_queried = True
                candidates.extend(lexical_candidates)

            if collection_was_queried:
                collections_queried.append(collection_name)

        candidates = self._dedupe_and_rank(candidates)
        chunks = candidates[: request.top_k]
        duration_ms = int((time.perf_counter() - started) * 1000)

        return RetrievalResult(
            chunks=chunks,
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=len(candidates),
                returned_count=len(chunks),
                filtered_count=0,
                source_filters=access_scope.source_filters,
                section_filters=request.section_filters,
                collections_queried=collections_queried,
                payload_filter=payload_filter.model_dump(mode="json", by_alias=True, exclude_none=True),
                duration_ms=duration_ms,
                topic_id=request.topic_id,
                topic_tags=request.topic_tags,
            ),
        )

    def _lexical_candidates(
        self,
        collection_name: str,
        payload_filter: models.Filter,
        question: str,
    ) -> list[ChunkDocument]:
        # Paginate through every accessible chunk (bounded by the scan cap) so a
        # page whose title matches the question is found regardless of where it
        # sits in the collection. Scanning only the first page silently misses
        # title matches once the corpus grows past one batch, which makes short
        # queries fail even when the page exists.
        scan_cap = self.settings.retrieval_lexical_scan_limit
        if scan_cap <= 0:
            scan_cap = _LEXICAL_SCAN_HARD_CAP
        batch_size = min(_LEXICAL_SCAN_BATCH, scan_cap)
        candidates: list[ChunkDocument] = []
        scanned = 0
        offset = None
        while scanned < scan_cap:
            try:
                points, offset = self.client.scroll(
                    collection_name=collection_name,
                    scroll_filter=payload_filter,
                    limit=min(batch_size, scan_cap - scanned),
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            except (UnexpectedResponse, ValueError):
                break
            if not points:
                break
            scanned += len(points)
            for point in points:
                if not point.payload:
                    continue
                chunk = self._chunk_from_payload(point.payload, score=0.0)
                lexical_score = lexical_relevance_score(question, chunk)
                if lexical_score > 0:
                    candidates.append(chunk.model_copy(update={"score": 100.0 + lexical_score}))
            if offset is None:
                break
        return candidates

    def _dedupe_and_rank(self, candidates: list[ChunkDocument]) -> list[ChunkDocument]:
        deduped: dict[str, ChunkDocument] = {}
        for candidate in candidates:
            existing = deduped.get(candidate.chunk_id)
            if existing is None or candidate.score > existing.score:
                deduped[candidate.chunk_id] = candidate
        ranked = list(deduped.values())
        ranked.sort(key=lambda chunk: (-chunk.score, chunk.title, chunk.chunk_index))
        return ranked

    async def ready(self) -> bool:
        try:
            self.client.get_collections()
        except (UnexpectedResponse, ValueError):
            return False
        return True

    def _collections_for_request(self, request: RetrievalRequest) -> list[str]:
        source_filters = set(request.access_scope.source_filters if request.access_scope else request.source_filters)
        collection_names = self.settings.retrieval_collection_list
        if not source_filters:
            return collection_names

        filtered: list[str] = []
        for collection_name in collection_names:
            if "onenote" in source_filters and collection_name == self.settings.onenote_vector_collection:
                filtered.append(collection_name)
        return filtered

    @staticmethod
    def build_payload_filter(
        access_scope: AccessScope,
        *,
        section_filters: list[str] | None = None,
        focus_source_item_ids: list[str] | None = None,
    ) -> models.Filter:
        acl_tags = access_scope.allowed_acl_tags or ["__no_allowed_acl_tags__"]
        must: list[models.FieldCondition] = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=access_scope.tenant_id),
            ),
            models.FieldCondition(
                key="acl_tags",
                match=models.MatchAny(any=acl_tags),
            ),
        ]
        if access_scope.source_filters:
            must.append(
                models.FieldCondition(
                    key="source_system",
                    match=models.MatchAny(any=access_scope.source_filters),
                )
            )
        section_names = [value.strip() for value in section_filters or [] if value.strip()]
        if section_names:
            must.append(
                models.FieldCondition(
                    key="metadata.section_name",
                    match=models.MatchAny(any=section_names),
                )
            )
        if focus_source_item_ids:
            focus = list(focus_source_item_ids)
            # Match the page itself OR a readable attachment belonging to it, so a
            # focused page keeps its attachment chunks eligible as evidence.
            must.append(
                models.Filter(
                    should=[
                        models.FieldCondition(key="source_item_id", match=models.MatchAny(any=focus)),
                        models.FieldCondition(
                            key="metadata.parent_source_item_id", match=models.MatchAny(any=focus)
                        ),
                    ]
                )
            )
        return models.Filter(must=must)

    def _chunk_from_payload(self, payload: dict[str, Any], *, score: float) -> ChunkDocument:
        return ChunkDocument(
            tenant_id=str(payload["tenant_id"]),
            source_system=str(payload["source_system"]),
            source_container=str(payload["source_container"]),
            source_item_id=str(payload["source_item_id"]),
            source_url=str(payload["source_url"]),
            title=str(payload["title"]),
            section_path=payload.get("section_path"),
            last_modified_utc=_parse_datetime(payload.get("last_modified_utc")),
            acl_tags=list(payload.get("acl_tags") or []),
            acl_bindings=[AclBinding(**binding) for binding in payload.get("acl_bindings") or []],
            content_hash=str(payload["content_hash"]),
            chunk_id=str(payload.get("chunk_id") or ""),
            chunk_index=int(payload["chunk_index"]),
            chunk_text=str(payload["chunk_text"]),
            embedding_model=str(payload.get("embedding_model") or self.settings.default_embedding_provider),
            language=str(payload.get("language") or "en"),
            tags=list(payload.get("tags") or []),
            metadata=dict(payload.get("metadata") or {}),
            score=score,
        )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now().astimezone()


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
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "about",
    "give",
    "tell",
    "whate",
    "whats",
    "page",
}


def lexical_relevance_score(question: str, chunk: ChunkDocument) -> float:
    question_tokens = _content_tokens(question)
    if not question_tokens:
        return 0.0
    if _is_value_reference_only(question, chunk.chunk_text):
        return 0.0

    title_tokens = _content_tokens(chunk.title)
    section_tokens = _content_tokens(chunk.section_path or "")
    body_tokens = _content_tokens(chunk.chunk_text)
    tag_tokens = _content_tokens(" ".join(chunk.tags))
    all_tokens = title_tokens | section_tokens | body_tokens | tag_tokens
    overlap = question_tokens.intersection(all_tokens)
    fuzzy_score = fuzzy_metadata_relevance_score(question, chunk)
    if not overlap and fuzzy_score <= 0:
        return 0.0

    title_overlap = question_tokens.intersection(title_tokens)
    section_overlap = question_tokens.intersection(section_tokens)
    coverage = len(overlap) / len(question_tokens)
    score = (
        len(overlap)
        + (coverage * 2.0)
        + (len(title_overlap) * 3.0)
        + (len(section_overlap) * 0.75)
        + fuzzy_score
    )
    key_phrase = _question_key_phrase(question)
    if key_phrase:
        if _contains_phrase(chunk.title, key_phrase):
            score += 12.0
        if _contains_phrase(chunk.section_path or "", key_phrase):
            score += 4.0
        if _contains_phrase(chunk.chunk_text, key_phrase):
            score += 3.0
        if _line_with_phrase_has_label(chunk.chunk_text, key_phrase):
            score += 10.0
    if _is_value_question(question) and _value_signal_present(chunk.chunk_text):
        score += 4.0
    return score


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


def _question_key_phrase(question: str) -> str:
    canonical_phrase = canonical_key_phrase(question)
    if canonical_phrase:
        return canonical_phrase
    tokens = [token for token in re.findall(r"[^\W_]+", question.lower()) if token not in _STOP_WORDS]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[-4:])


def _contains_phrase(value: str, phrase: str) -> bool:
    if not phrase:
        return False
    normalized_value = _normalized_words(value)
    return any(variant in normalized_value for variant in _phrase_variants(phrase))


def _phrase_variants(phrase: str) -> list[str]:
    normalized_phrase = _normalized_words(phrase)
    tokens = normalized_phrase.split()
    if len(tokens) <= 2:
        return [normalized_phrase] if normalized_phrase else []
    variants = [normalized_phrase]
    for size in range(min(3, len(tokens)), 1, -1):
        suffix = " ".join(tokens[-size:])
        if suffix not in variants:
            variants.append(suffix)
        prefix = " ".join(tokens[:size])
        if prefix not in variants:
            variants.append(prefix)
    return variants


def _normalized_words(value: str) -> str:
    return " ".join(_normalize_token(token) for token in re.findall(r"[^\W_]+", value.lower()))


def _line_with_phrase_has_label(value: str, phrase: str) -> bool:
    for line in value.splitlines():
        if _contains_phrase(line, phrase) and ":" in line:
            return True
    return False


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


def _is_value_reference_only(question: str, value: str) -> bool:
    if not _is_value_question(question):
        return False
    key_phrase = _question_key_phrase(question)
    if not key_phrase or not _contains_phrase(value, key_phrase):
        return False
    return not _value_signal_present(value)
