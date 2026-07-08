from shared_schemas import AppSettings
from shared_schemas.embeddings import Embedder, create_embedder


def build_query_embedder(settings: AppSettings) -> Embedder:
    """Query-side embedder. Resolves through the shared factory so query vectors
    always come from the same model and dimension as the indexed chunk vectors.

    When a Redis host is configured, the embedder is wrapped in a best-effort
    cache so repeated questions reuse their vector instead of re-embedding."""
    embedder = create_embedder(settings)
    if settings.query_embedding_cache_enabled and settings.redis_host:
        from rag_api.adapters.embedding_cache import RedisQueryEmbeddingCache

        return RedisQueryEmbeddingCache(embedder, settings)
    return embedder
