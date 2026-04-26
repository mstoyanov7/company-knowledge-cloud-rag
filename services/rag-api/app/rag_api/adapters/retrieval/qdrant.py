from __future__ import annotations

import time
from datetime import datetime
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

from rag_api.adapters.embeddings import DeterministicQueryEmbedder


class QdrantAclRetriever:
    name = "qdrant-vector-acl"

    def __init__(self, settings: AppSettings, *, embedder: DeterministicQueryEmbedder | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or DeterministicQueryEmbedder(settings)
        self.client = QdrantClient(url=settings.qdrant_url)

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        if request.access_scope is None:
            raise ValueError("ACL-aware retrieval requires an access scope.")

        access_scope = request.access_scope
        collections = self._collections_for_request(request)
        payload_filter = self.build_payload_filter(access_scope)
        query_vector = self.embedder.embed_text(request.question)
        candidates: list[ChunkDocument] = []
        collections_queried: list[str] = []

        for collection_name in collections:
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
                continue

            collections_queried.append(collection_name)
            for point in response.points:
                if point.payload:
                    candidates.append(self._chunk_from_payload(point.payload, score=float(point.score or 0.0)))

        candidates.sort(key=lambda chunk: (-chunk.score, chunk.title, chunk.chunk_index))
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
                collections_queried=collections_queried,
                payload_filter=payload_filter.model_dump(mode="json", by_alias=True, exclude_none=True),
                duration_ms=duration_ms,
            ),
        )

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
            if "sharepoint" in source_filters and collection_name == self.settings.sharepoint_vector_collection:
                filtered.append(collection_name)
            if "onenote" in source_filters and collection_name == self.settings.onenote_vector_collection:
                filtered.append(collection_name)
        return filtered or collection_names

    @staticmethod
    def build_payload_filter(access_scope: AccessScope) -> models.Filter:
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
