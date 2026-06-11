from __future__ import annotations

import math

from rag_api.evaluation.metrics import hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank


def test_reciprocal_rank_uses_first_relevant_position() -> None:
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == 0.5
    assert reciprocal_rank(["b", "a", "c"], {"b"}) == 1.0
    assert reciprocal_rank(["x", "y"], {"b"}) == 0.0


def test_hit_and_recall_at_k() -> None:
    ranked = ["a", "b", "c", "d"]
    assert hit_at_k(ranked, {"c"}, k=3) is True
    assert hit_at_k(ranked, {"d"}, k=3) is False
    assert recall_at_k(ranked, {"a", "d"}, k=2) == 0.5
    assert recall_at_k(ranked, {"a", "b"}, k=2) == 1.0


def test_ndcg_rewards_higher_ranking() -> None:
    top = ndcg_at_k(["rel", "x", "y"], {"rel"}, k=3)
    lower = ndcg_at_k(["x", "y", "rel"], {"rel"}, k=3)
    assert top == 1.0
    assert lower < top
    assert math.isclose(lower, 1.0 / math.log2(4))


def test_empty_relevant_set_is_perfect_by_convention() -> None:
    assert recall_at_k(["a"], set(), k=1) == 1.0
    assert ndcg_at_k(["a"], set(), k=1) == 1.0
