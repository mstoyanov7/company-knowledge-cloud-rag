from __future__ import annotations

import hashlib
import math
import re
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from shared_schemas.config import AppSettings

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

TOKEN_HASH_PROVIDER = "token-hash-v1"
OLLAMA_PROVIDER = "ollama"


class EmbeddingError(RuntimeError):
    """Raised when a real embedding backend cannot produce usable vectors.

    Kept distinct from generic errors so callers (retrieval, ingestion) can tell
    "the embedding service is unreachable / misconfigured" apart from "no results".
    """


class Embedder(Protocol):
    """Shared contract for query-side and index-side embedding.

    The index side and the query side MUST resolve to the same provider and the
    same ``vector_size``; cosine search over vectors from two different models is
    silently meaningless, not an error. ``create_embedder`` is the single place
    that guarantees both sides agree.
    """

    @property
    def vector_size(self) -> int: ...

    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


def embed_text_token_hash(text: str, *, vector_size: int) -> list[float]:
    """Create a deterministic lexical vector suitable for local tests.

    This is not a production embedding model. It preserves enough token overlap
    signal for the local proof of concept to retrieve different chunks for
    different questions without external model dependencies. Real semantic
    retrieval uses :class:`OllamaEmbedder`.
    """
    vector = [0.0] * vector_size
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return _fallback_vector(text, vector_size=vector_size)

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % vector_size
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return _fallback_vector(text, vector_size=vector_size)
    return [value / magnitude for value in vector]


def _fallback_vector(text: str, *, vector_size: int) -> list[float]:
    vector: list[float] = []
    seed = text.encode("utf-8") or b"empty"
    while len(vector) < vector_size:
        seed = hashlib.blake2b(seed, digest_size=32).digest()
        for byte in seed:
            vector.append((byte / 255.0) * 2.0 - 1.0)
            if len(vector) == vector_size:
                break
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector]


class TokenHashEmbedder:
    """Deterministic, offline lexical embedder. Test/no-network fallback only."""

    def __init__(self, *, vector_size: int) -> None:
        self._vector_size = vector_size

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def embed_text(self, text: str) -> list[float]:
        return embed_text_token_hash(text, vector_size=self._vector_size)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    # Lexical fallback has no query/document asymmetry; role methods are aliases.
    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_texts(texts)


class OllamaEmbedder:
    """Real semantic embeddings via an Ollama (OpenAI-compatible) endpoint.

    Calls ``POST {base_url}/embeddings`` with ``{"model", "input": [...]}`` and
    expects ``{"data": [{"embedding": [...]}]}`` (the OpenAI embeddings shape that
    Ollama exposes on its ``/v1`` API). Synchronous on purpose: the retriever and
    the ingestion worker both call embedding from synchronous code paths.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        vector_size: int,
        query_prefix: str = "",
        document_prefix: str = "",
        timeout_seconds: float = 120.0,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._vector_size = vector_size
        # Task instruction prefixes (e.g. nomic-embed-text's "search_query:" /
        # "search_document:"). The model was trained with these; omitting them
        # degrades retrieval and breaks query<->document alignment.
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([f"{self.query_prefix}{text}"])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_texts([f"{self.document_prefix}{text}" for text in texts])

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = self._request_embeddings(texts)
        if len(payload) != len(texts):
            raise EmbeddingError(
                f"Embedding backend returned {len(payload)} vectors for {len(texts)} inputs."
            )
        for vector in payload:
            if len(vector) != self._vector_size:
                raise EmbeddingError(
                    f"Embedding model '{self.model}' returned dimension {len(vector)}, "
                    f"but EMBEDDING_VECTOR_SIZE is {self._vector_size}. "
                    "Set EMBEDDING_VECTOR_SIZE to match the model and re-index."
                )
        return payload

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        import httpx

        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "input": texts}
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, json=body, headers=headers)
                    response.raise_for_status()
                    data = response.json().get("data", [])
                    ordered = sorted(data, key=lambda item: item.get("index", 0))
                    return [[float(value) for value in item["embedding"]] for item in ordered]
            except Exception as error:  # network, HTTP, or shape errors
                last_error = error
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * attempt)
        raise EmbeddingError(
            f"Could not reach embedding backend at {url} after {self.max_attempts} attempts: {last_error}"
        ) from last_error


def create_embedder(settings: "AppSettings") -> Embedder:
    """Resolve the configured embedder. Single source of truth for both services.

    Keyed on ``DEFAULT_EMBEDDING_PROVIDER``. ``ollama`` is the real semantic path;
    ``token-hash-v1`` is the offline/test fallback. Both sides of the system call
    this so the query and index vectors are always from the same model + size.
    """
    provider = (settings.default_embedding_provider or OLLAMA_PROVIDER).strip().lower()
    if provider in {TOKEN_HASH_PROVIDER, "token-hash", "deterministic"}:
        return TokenHashEmbedder(vector_size=settings.embedding_vector_size)
    if provider in {OLLAMA_PROVIDER, "openai", "openai-compatible"}:
        query_prefix, document_prefix = _task_prefixes_for_model(settings.embedding_model_name)
        return OllamaEmbedder(
            base_url=settings.resolved_embedding_base_url,
            api_key=settings.resolved_embedding_api_key,
            model=settings.embedding_model_name,
            vector_size=settings.embedding_vector_size,
            query_prefix=query_prefix,
            document_prefix=document_prefix,
            timeout_seconds=settings.llm_request_timeout_seconds,
        )
    raise EmbeddingError(f"Unknown embedding provider '{settings.default_embedding_provider}'.")


def _task_prefixes_for_model(model: str) -> tuple[str, str]:
    """Return (query_prefix, document_prefix) for instruction-tuned embedders.

    nomic-embed-text requires "search_query:" / "search_document:" task prefixes.
    Models without this convention get empty prefixes.
    """
    if "nomic" in model.lower():
        return "search_query: ", "search_document: "
    return "", ""
