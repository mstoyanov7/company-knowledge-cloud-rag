"""Deterministic semantic retrieval over pre-computed embedding vectors.

The semantic evaluation tier measures the *actual* retrieval configuration
(real ``nomic-embed-text`` vectors) while staying fully reproducible offline:
the vectors are frozen in a fixture file produced once by
``eval/build_semantic_fixture.py`` against a local Ollama.

Behaviour mirrors :class:`MockRetriever` exactly for ACL, tenant, source and
section filtering; only the relevance score differs - cosine similarity
between the frozen query vector and the frozen chunk vectors. Query variants
missing from the fixture fall back to the lexical score of the parent class,
so the retriever degrades gracefully instead of failing.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from shared_schemas import AccessScope, AppSettings, ChunkDocument, RetrievalMetadata, RetrievalRequest, RetrievalResult

from rag_api.adapters.retrieval.mock import MockRetriever, _tokenize


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class FixtureSemanticRetriever(MockRetriever):
    name = "semantic-fixture"

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        fixture_path = Path(getattr(settings, "semantic_fixture_path", "") or "eval/datasets/semantic_fixture.json")
        if not fixture_path.is_absolute():
            fixture_path = Path.cwd() / fixture_path
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self._doc_vectors: dict[str, list[float]] = fixture["documents"]
        self._query_vectors: dict[str, list[float]] = fixture["queries"]
        self._min_score = float(getattr(settings, "retrieval_min_semantic_score", 0.0) or 0.0)
        # Small per-token lexical bonus so keyword-anchored pages (direct /
        # procedural) keep their edge while paraphrases still rank by meaning.
        self._lexical_weight = float(getattr(settings, "retrieval_lexical_weight", 0.0) or 0.0)

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        query_vector = self._query_vectors.get(_sha1(request.question))
        if query_vector is None:
            # Unknown variant (not in the fixture): degrade to lexical scoring.
            return await super().retrieve(request)

        started = time.perf_counter()
        question_tokens = _tokenize(request.question) if self._lexical_weight else set()
        access_scope = request.access_scope or AccessScope(
            user_id=request.user_context.user_id,
            email=request.user_context.email,
            tenant_id=request.user_context.tenant_id,
            allowed_acl_tags=request.user_context.acl_tags,
            groups=request.user_context.groups,
            roles=request.user_context.roles,
            source_filters=request.source_filters,
            is_admin=request.user_context.is_admin,
        )
        allowed_acl_tags = set(access_scope.allowed_acl_tags)
        source_filters = set(access_scope.source_filters)
        section_filters = list(dict.fromkeys(value.strip() for value in request.section_filters if value.strip()))
        section_filter_set = set(section_filters)
        focus_ids = set(request.focus_source_item_ids)

        scored: list[ChunkDocument] = []
        filtered_count = 0
        for document in self.documents:
            if focus_ids:
                parent_id = (document.metadata or {}).get("parent_source_item_id")
                if document.source_item_id not in focus_ids and parent_id not in focus_ids:
                    filtered_count += 1
                    continue
            if source_filters and document.source_system not in source_filters:
                filtered_count += 1
                continue
            section_name = str((document.metadata or {}).get("section_name") or "")
            if section_filter_set and section_name not in section_filter_set:
                filtered_count += 1
                continue
            if not access_scope.is_admin and not allowed_acl_tags.intersection(set(document.acl_tags)):
                filtered_count += 1
                continue

            chunk_key = f"{document.source_item_id}#{document.chunk_index}"
            doc_vector = self._doc_vectors.get(chunk_key)
            if doc_vector is None:
                continue
            similarity = _cosine(query_vector, doc_vector)
            if similarity < self._min_score:
                continue
            score = float(similarity)
            if self._lexical_weight and question_tokens:
                doc_text = " ".join(
                    [document.title, document.section_path or "", document.chunk_text, " ".join(document.tags)]
                )
                score += self._lexical_weight * len(question_tokens & _tokenize(doc_text))
            metadata = {**(document.metadata or {}), "semantic_score": float(similarity)}
            scored.append(document.model_copy(update={"score": score, "metadata": metadata}))

        scored.sort(key=lambda item: (-item.score, item.title, item.chunk_index))
        top_k = min(request.top_k, self.settings.mock_top_k)
        chunks = scored[:top_k]
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RetrievalResult(
            chunks=chunks,
            metadata=RetrievalMetadata(
                strategy=self.name,
                access_scope=access_scope,
                requested_top_k=request.top_k,
                candidate_count=len(scored),
                returned_count=len(chunks),
                filtered_count=filtered_count,
                source_filters=access_scope.source_filters,
                section_filters=section_filters,
                collections_queried=["semantic-fixture"],
                duration_ms=duration_ms,
                payload_filter={
                    "tenant_id": access_scope.tenant_id,
                    "acl_tags": access_scope.allowed_acl_tags,
                    "source_system": access_scope.source_filters,
                    "section_filters": section_filters,
                    "topic_id": request.topic_id,
                    "topic_tags": request.topic_tags,
                },
                topic_id=request.topic_id,
                topic_tags=request.topic_tags,
            ),
        )
