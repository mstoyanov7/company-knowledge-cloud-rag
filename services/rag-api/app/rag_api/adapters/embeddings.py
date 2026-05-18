from shared_schemas import AppSettings
from shared_schemas.embeddings import embed_text_token_hash


class DeterministicQueryEmbedder:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def embed_text(self, text: str) -> list[float]:
        return embed_text_token_hash(text, vector_size=self.settings.embedding_vector_size)
