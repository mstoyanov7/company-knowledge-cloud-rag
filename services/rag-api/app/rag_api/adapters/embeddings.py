from __future__ import annotations

import hashlib

from shared_schemas import AppSettings


class DeterministicQueryEmbedder:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def embed_text(self, text: str) -> list[float]:
        vector: list[float] = []
        seed = text.encode("utf-8")
        while len(vector) < self.settings.embedding_vector_size:
            seed = hashlib.blake2b(seed, digest_size=32).digest()
            for byte in seed:
                vector.append((byte / 255.0) * 2.0 - 1.0)
                if len(vector) == self.settings.embedding_vector_size:
                    break
        return vector
