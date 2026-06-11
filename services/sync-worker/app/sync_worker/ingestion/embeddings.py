from shared_schemas import AppSettings, ChunkDocument
from shared_schemas.embeddings import create_embedder


class ChunkEmbedder:
    """Index-side embedder. Resolves through the shared factory so indexed chunk
    vectors always match the query-side model and dimension."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.embedder = create_embedder(settings)

    def embed_chunks(self, chunks: list[ChunkDocument]) -> list[list[float]]:
        return self.embedder.embed_documents([chunk.chunk_text for chunk in chunks])


# Backwards-compatible alias for the previous name.
DeterministicEmbedder = ChunkEmbedder
