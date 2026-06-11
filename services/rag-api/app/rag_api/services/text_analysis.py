"""Shared lexical primitives for answer assembly and inventory matching.

These are deliberately small, dependency-free helpers (tokenization, light
stemming, phrase matching) extracted from ``answer_service`` so feature modules
(e.g. ``inventory``) can reuse them without importing the whole answer service.
Kept separate from the similarly named helpers in ``retrieval_ranking``: their
stop-word sets differ, and merging them would change behaviour.
"""

from __future__ import annotations

import re

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "info",
    "information",
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
    "there",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "about",
    "give",
    "tell",
    "whate",
    "whats",
    "based",
    "company",
    "following",
    "means",
    "note",
    "notes",
    "page",
    "provided",
    "says",
    "source",
    "states",
    "that",
    "this",
    "you",
    "your",
}


def _content_tokens(value: str) -> set[str]:
    return {
        _normalize_token(token)
        for token in re.findall(r"[^\W_]+", value.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _normalize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _normalized_words(value: str) -> str:
    return " ".join(_normalize_token(token) for token in re.findall(r"[^\W_]+", value.lower()))


def _contains_phrase(value: str, phrase: str) -> bool:
    if not phrase:
        return False
    normalized_value = _normalized_words(value)
    return any(variant in normalized_value for variant in _phrase_variants(phrase))


def _phrase_variants(phrase: str) -> list[str]:
    normalized_phrase = _normalized_words(phrase)
    tokens = normalized_phrase.split()
    if len(tokens) <= 2:
        return [normalized_phrase] if normalized_phrase else []
    variants = [normalized_phrase]
    for size in range(min(3, len(tokens)), 1, -1):
        suffix = " ".join(tokens[-size:])
        if suffix not in variants:
            variants.append(suffix)
        prefix = " ".join(tokens[:size])
        if prefix not in variants:
            variants.append(prefix)
    return variants
