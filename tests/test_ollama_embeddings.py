from __future__ import annotations

import math

import pytest

from shared_schemas import AppSettings
from shared_schemas.embeddings import EmbeddingError, OllamaEmbedder, embed_text_token_hash

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# A synonym query with NO content-token overlap with the related passage. This is
# the case lexical token-hash cannot solve and real semantic embeddings can.
QUERY = "What is the paid time off allowance?"
RELATED = "Staff receive twenty vacation days each calendar year."
UNRELATED = "The office kitchen is cleaned every Friday evening."


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _ollama_embedder() -> OllamaEmbedder:
    settings = AppSettings()
    return OllamaEmbedder(
        base_url=settings.resolved_embedding_base_url,
        api_key=settings.resolved_embedding_api_key,
        model=EMBED_MODEL,
        vector_size=EMBED_DIM,
        query_prefix="search_query: ",
        document_prefix="search_document: ",
        timeout_seconds=15.0,
        max_attempts=1,
    )


def _require_ollama(embedder: OllamaEmbedder) -> None:
    try:
        embedder.embed_text("connectivity probe")
    except EmbeddingError as error:
        pytest.skip(f"Ollama embedding backend unavailable: {error}")


def test_semantic_embedding_beats_lexical_on_synonyms() -> None:
    embedder = _ollama_embedder()
    _require_ollama(embedder)

    # Mirror production: query goes through embed_query (search_query: prefix),
    # passages through embed_documents (search_document: prefix).
    query = embedder.embed_query(QUERY)
    related, unrelated = embedder.embed_documents([RELATED, UNRELATED])

    # Real semantic embeddings rank the paraphrase above the unrelated sentence...
    assert _cosine(query, related) > _cosine(query, unrelated)

    # ...whereas the lexical token-hash fallback cannot tell them apart, because
    # the query shares no tokens with either. This contrast is the whole point of
    # Phase 1: the system now retrieves on meaning, not shared words.
    th_query = embed_text_token_hash(QUERY, vector_size=EMBED_DIM)
    th_related = embed_text_token_hash(RELATED, vector_size=EMBED_DIM)
    assert _cosine(th_query, th_related) <= _cosine(query, related)
