from shared_schemas import AppSettings, ChunkDocument
from shared_schemas.embeddings import embed_text_token_hash


class DeterministicEmbedder:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def embed_chunks(self, chunks: list[ChunkDocument]) -> list[list[float]]:
        return [self._embed_text(chunk.chunk_text) for chunk in chunks]

    def _embed_text(self, text: str) -> list[float]:
        return embed_text_token_hash(text, vector_size=self.settings.embedding_vector_size)
