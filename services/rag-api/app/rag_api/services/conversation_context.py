"""Resolve conversational follow-up questions into standalone questions.

When a user asks a follow-up that relies on earlier turns ("how do I run it?",
"what about deployment?"), this module rewrites it into a self-contained
question by carrying the subject established earlier in the same chat session.
Only the *retrieval/understanding* question is enriched - answers stay grounded
in the retrieved OneNote context.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
from typing import Protocol

from rag_api.services.query_understanding import analyze_question


class _Turn(Protocol):
    role: str
    content: str


# Words that point back to something said earlier in the conversation.
_ANAPHORA = re.compile(
    r"\b(it|its|it's|this|that|these|those|they|them|their|there|same|"
    r"above|previous|former|latter|former one|that one)\b",
    re.IGNORECASE,
)
_REFERENTIAL_NOUN = re.compile(
    r"\bthe (project|projects|setup|repo|repository|page|guide|app|application|"
    r"service|system|tool|process|steps?|config(?:uration)?|document|doc)\b",
    re.IGNORECASE,
)
_FOLLOWUP_OPENER = re.compile(
    r"^\s*(what about|how about|and what|and how|what else|anything else|"
    r"tell me more|more on|more about|continue|also|then)\b",
    re.IGNORECASE,
)

# Generic nouns that do not, on their own, identify a subject.
_GENERIC = {
    "project",
    "projects",
    "setup",
    "page",
    "guide",
    "app",
    "application",
    "service",
    "system",
    "tool",
    "process",
    "step",
    "steps",
    "config",
    "configuration",
    "document",
    "doc",
    "thing",
    "things",
    "detail",
    "details",
    "info",
    "information",
    "note",
    "notes",
}


def _content_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2 and token not in _GENERIC]


def is_followup_question(question: str) -> bool:
    """True when a question depends on earlier turns to be understood."""
    if _ANAPHORA.search(question) or _REFERENTIAL_NOUN.search(question) or _FOLLOWUP_OPENER.search(question):
        return True
    # A "thin" question (no concrete subject of its own) is treated as a follow-up.
    analysis = analyze_question(question)
    strong = [entity for entity in analysis.important_entities if entity.lower() not in _GENERIC and len(entity) > 2]
    return len(strong) <= 1 and len(_content_tokens(question)) <= 2


def _subject_phrase(text: str) -> str:
    analysis = analyze_question(text)
    for phrase in analysis.key_phrases:
        tokens = [token for token in re.findall(r"[a-z0-9]+", phrase.lower()) if token not in _GENERIC]
        if len(tokens) >= 2:
            return phrase.strip()
    candidates = [
        entity.strip()
        for entity in analysis.important_entities
        if entity.lower() not in _GENERIC and len(entity) > 2
    ]
    return candidates[0] if candidates else ""


def carried_subject(history: Sequence[_Turn], *, max_turns: int = 8) -> str:
    """The most recent subject a user established earlier in the session."""
    recent = list(history)[-max_turns:]
    for turn in reversed(recent):
        if getattr(turn, "role", None) != "user":
            continue
        subject = _subject_phrase(getattr(turn, "content", "") or "")
        if subject:
            return subject
    return ""


def contextualize_question(question: str, history: Sequence[_Turn] | None) -> str:
    """Return a standalone version of ``question`` using prior conversation turns.

    Returns ``question`` unchanged when there is no history, when the question
    already names its own subject, or when no prior subject is available.
    """
    if not history:
        return question
    if not is_followup_question(question):
        return question
    subject = carried_subject(history)
    if not subject or subject.lower() in question.lower():
        return question
    return f"{question} {subject}".strip()
