from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from shared_schemas import AppSettings
from shared_schemas.embeddings import Embedder

logger = logging.getLogger("rag_api.embedding_cache")


class RedisQueryEmbeddingCache:
    """Wrap a query-side :class:`Embedder` and cache ``embed_query`` vectors in Redis.

    A repeated question produces the same vector, so caching it skips a model
    round-trip and shaves the embedding step off retrieval latency.

    The cache key is derived only from the question text plus the model identity
    (provider, model, vector size) — never from the user or the access scope.
    Embeddings are scope-independent, so the cache cannot leak content across
    access scopes; access control still happens afterwards in the retriever and
    answer pipeline, exactly as before.

    The cache is best-effort: any Redis error disables it for the process and the
    call falls back to the wrapped embedder, so answering never fails because of a
    cache problem. Only ``embed_query`` is cached; every other method delegates
    straight to the wrapped embedder.
    """

    def __init__(self, inner: Embedder, settings: AppSettings, *, client: Any | None = None) -> None:
        self._inner = inner
        self._ttl = max(1, int(settings.query_embedding_cache_ttl_seconds))
        self._prefix = (
            f"rag:qemb:{settings.default_embedding_provider}:"
            f"{settings.embedding_model_name}:{inner.vector_size}:"
        )
        self._client = client if client is not None else _build_client(settings)

    @property
    def vector_size(self) -> int:
        return self._inner.vector_size

    def embed_text(self, text: str) -> list[float]:
        return self._inner.embed_text(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_texts(texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._client is None:
            return self._inner.embed_query(text)
        key = self._prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = self._get(key)
        if cached is not None:
            return cached
        vector = self._inner.embed_query(text)
        self._set(key, vector)
        return vector

    def _get(self, key: str) -> list[float] | None:
        try:
            raw = self._client.get(key)
        except Exception as error:  # noqa: BLE001 - the cache must never break answering
            self._disable(error)
            return None
        if not raw:
            return None
        try:
            return [float(value) for value in json.loads(raw)]
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def _set(self, key: str, vector: list[float]) -> None:
        try:
            self._client.setex(key, self._ttl, json.dumps(vector))
        except Exception as error:  # noqa: BLE001 - cache writes are best-effort
            self._disable(error)

    def _disable(self, error: Exception) -> None:
        if self._client is not None:
            logger.warning("event=query_embedding_cache_disabled reason=%s", error)
        self._client = None


def _build_client(settings: AppSettings) -> Any | None:
    if not settings.redis_host:
        return None
    try:
        import redis
    except ImportError:
        logger.warning("event=query_embedding_cache_unavailable reason=redis_not_installed")
        return None
    try:
        return redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
    except Exception as error:  # noqa: BLE001 - fall back to no cache on any setup error
        logger.warning("event=query_embedding_cache_unavailable reason=%s", error)
        return None
