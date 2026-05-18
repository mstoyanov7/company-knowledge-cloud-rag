from __future__ import annotations

import re

from shared_schemas import ChunkDocument


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


class KeywordOverlapReranker:
    name = "keyword-overlap-reranker"

    def rerank(self, question: str, chunks: list[ChunkDocument], *, top_k: int) -> list[ChunkDocument]:
        question_tokens = _tokenize(question)
        ranked: list[ChunkDocument] = []
        for chunk in chunks:
            chunk_tokens = _tokenize(
                " ".join(
                    [
                        chunk.title,
                        chunk.section_path or "",
                        chunk.chunk_text,
                        " ".join(chunk.tags),
                    ]
                )
            )
            overlap = question_tokens.intersection(chunk_tokens)
            coverage = len(overlap) / len(question_tokens) if question_tokens else 0.0
            score = chunk.score + (len(overlap) * 2.0) + coverage
            ranked.append(chunk.model_copy(update={"score": score}))
        ranked.sort(key=lambda item: (-item.score, item.title, item.chunk_index))
        return ranked[:top_k]
