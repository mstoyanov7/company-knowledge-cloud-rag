from __future__ import annotations

from shared_schemas import AppSettings

from rag_api.adapters.embedding_cache import RedisQueryEmbeddingCache
from rag_api.adapters.embeddings import build_query_embedder


class _FakeRedis:
    """Minimal in-memory stand-in for the redis client (get/setex only)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.gets = 0
        self.sets = 0

    def get(self, key: str):
        self.gets += 1
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.sets += 1
        self.store[key] = value


class _CountingEmbedder:
    """Embedder that records how often it actually computes a vector."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def vector_size(self) -> int:
        return 4

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return [float(len(text)), 1.0, 2.0, 3.0]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_query(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_texts(texts)


def _settings() -> AppSettings:
    return AppSettings(redis_host="redis", query_embedding_cache_enabled=True)


def test_repeated_question_served_from_cache() -> None:
    inner = _CountingEmbedder()
    fake = _FakeRedis()
    cache = RedisQueryEmbeddingCache(inner, _settings(), client=fake)

    first = cache.embed_query("how do I reset my password")
    second = cache.embed_query("how do I reset my password")

    assert first == second
    assert inner.calls == 1  # embedded once; second call served from Redis
    assert fake.sets == 1


def test_distinct_questions_are_not_collapsed() -> None:
    inner = _CountingEmbedder()
    cache = RedisQueryEmbeddingCache(inner, _settings(), client=_FakeRedis())

    first = cache.embed_query("question one")
    second = cache.embed_query("a different question")

    assert first != second
    assert inner.calls == 2


def test_redis_failure_falls_back_to_embedder() -> None:
    class _BrokenRedis:
        def get(self, key: str):
            raise RuntimeError("connection refused")

        def setex(self, *args: object) -> None:
            raise RuntimeError("connection refused")

    inner = _CountingEmbedder()
    cache = RedisQueryEmbeddingCache(inner, _settings(), client=_BrokenRedis())

    vector = cache.embed_query("anything")

    assert vector == [len("anything"), 1.0, 2.0, 3.0]
    assert inner.calls == 1  # answered despite Redis being unreachable


def test_cache_disabled_when_no_redis_host() -> None:
    # Empty redis_host disables the cache wrapper entirely.
    settings = AppSettings(default_embedding_provider="token-hash-v1", redis_host="")
    embedder = build_query_embedder(settings)
    assert not isinstance(embedder, RedisQueryEmbeddingCache)


def test_cache_enabled_when_redis_host_set() -> None:
    settings = AppSettings(default_embedding_provider="token-hash-v1", redis_host="redis")
    embedder = build_query_embedder(settings)
    assert isinstance(embedder, RedisQueryEmbeddingCache)
