from __future__ import annotations

from shared_schemas.embeddings import embed_text_token_hash


def _dot(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))


def test_token_hash_embedding_prefers_shared_terms() -> None:
    question = embed_text_token_hash("benefits medical wellness", vector_size=64)
    benefits = embed_text_token_hash("review medical benefits and wellness options", vector_size=64)
    engineering = embed_text_token_hash("install docker and request repository access", vector_size=64)

    assert _dot(question, benefits) > _dot(question, engineering)
