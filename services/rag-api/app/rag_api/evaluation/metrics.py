"""Pure ranking-quality metrics for retrieval evaluation.

All functions take a ranked list of candidate ids (best first) and the set of
ids that are actually relevant, so they work for both the answer-level harness
(citations) and the embedding A/B harness (vector ranking).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Iterable[str]) -> float:
    """1 / (rank of the first relevant id), or 0.0 if none are relevant."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    for position, candidate in enumerate(ranked_ids, start=1):
        if candidate in relevant:
            return 1.0 / position
    return 0.0


def hit_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> bool:
    """Whether any relevant id appears in the top-k."""
    relevant = set(relevant_ids)
    return any(candidate in relevant for candidate in ranked_ids[:k])


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of relevant ids retrieved within the top-k."""
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    found = sum(1 for candidate in ranked_ids[:k] if candidate in relevant)
    return found / len(relevant)


def ndcg_at_k(ranked_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Binary-relevance nDCG@k. 1.0 means every relevant id is ranked at the top."""
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    dcg = 0.0
    for position, candidate in enumerate(ranked_ids[:k], start=1):
        if candidate in relevant:
            dcg += 1.0 / math.log2(position + 1)
    ideal_hits = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0
