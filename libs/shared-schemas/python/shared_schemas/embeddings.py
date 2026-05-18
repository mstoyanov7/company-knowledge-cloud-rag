from __future__ import annotations

import hashlib
import math
import re

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def embed_text_token_hash(text: str, *, vector_size: int) -> list[float]:
    """Create a deterministic lexical vector suitable for local tests.

    This is not a production embedding model. It preserves enough token overlap
    signal for the local proof of concept to retrieve different chunks for
    different questions without external model dependencies.
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
