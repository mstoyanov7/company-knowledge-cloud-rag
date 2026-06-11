"""Deterministic profile of the selected evidence, used to drive answer formatting.

The format of an answer should be decided by what the *collected evidence*
contains (code, steps, tabular facts, plain prose) and how many pages it spans
— never by mirroring the formatting of the source notes. This module inspects
the selected chunks and produces a short, dynamic instruction ("content plan")
that is appended to the system prompt for the generation call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CODE_LINE = re.compile(
    r"^\s*(?:\$ |> |#!|pip3? install|npm (?:install|run)|winget install|docker(?: compose)?\s|"
    r"kubectl\s|git (?:clone|checkout|pull|push)|curl\s|make\s|python3?\s|alembic\s|nw\s|"
    r"flutter\s|SELECT\s|INSERT\s|UPDATE\s|export [A-Z_]+=|[A-Z][A-Z0-9_]*=\S)",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*```")
_STEP_LINE = re.compile(r"^\s*(?:\d+[.)]\s+|step\s+\d+\b|[-*]\s+(?:first|then|next|finally)\b)", re.IGNORECASE)
_TABLE_LINE = re.compile(r"^\s*\|.+\|\s*$")
_VALUE_SIGNAL = re.compile(r"\b\d+(?:[.,:]\d+)?\s*(?:%|eur|usd|days?|hours?|minutes?|gb|mb|s\b)|\b\d{1,2}:\d{2}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    page_count: int
    attachment_count: int
    code_chunk_count: int
    has_code: bool
    has_steps: bool
    has_table: bool
    has_values: bool


def build_evidence_profile(chunks: list) -> EvidenceProfile:
    pages: set[str] = set()
    attachments = 0
    code_chunks = 0
    has_steps = False
    has_table = False
    has_values = False

    for chunk in chunks:
        metadata = getattr(chunk, "metadata", None) or {}
        if metadata.get("document_kind") == "attachment":
            attachments += 1
            parent = metadata.get("parent_source_item_id") or chunk.source_item_id
            pages.add(str(parent))
        else:
            pages.add(chunk.source_item_id)

        text = chunk.chunk_text or ""
        lines = text.splitlines()
        code_lines = sum(1 for line in lines if _CODE_LINE.match(line) or _FENCE.match(line))
        if code_lines >= 2 or chunk_kind_hint(chunk) in {"commands", "install", "configuration"}:
            code_chunks += 1
        if any(_STEP_LINE.match(line) for line in lines) or chunk_kind_hint(chunk) in {"procedure", "checklist"}:
            has_steps = True
        if sum(1 for line in lines if _TABLE_LINE.match(line)) >= 2:
            has_table = True
        if _VALUE_SIGNAL.search(text):
            has_values = True

    return EvidenceProfile(
        page_count=len(pages),
        attachment_count=attachments,
        code_chunk_count=code_chunks,
        has_code=code_chunks > 0,
        has_steps=has_steps,
        has_table=has_table,
        has_values=has_values,
    )


def chunk_kind_hint(chunk) -> str | None:
    kind = getattr(chunk, "chunk_kind", None)
    if kind:
        return str(kind)
    metadata = getattr(chunk, "metadata", None) or {}
    value = metadata.get("chunk_kind")
    return str(value) if value else None


def format_plan_instruction(profile: EvidenceProfile) -> str:
    """Short dynamic instruction describing how to lay out the answer."""
    parts: list[str] = []

    if profile.page_count >= 2:
        parts.append(
            f"The evidence spans {profile.page_count} different pages: weave their facts into ONE seamless answer "
            "that reads as if it came from a single source — do not answer page by page and do not repeat "
            "the same fact from two pages."
        )
    if profile.has_code and profile.page_count >= 2:
        parts.append(
            "Commands or code appear in several blocks: merge them into a single coherent fenced code block "
            "in logical execution order (with a language hint), instead of separate per-page fragments; "
            "only keep separate blocks when they belong to clearly different tasks."
        )
    elif profile.has_code:
        parts.append(
            "The evidence contains commands or code: present them in fenced code blocks with a language hint, "
            "in logical execution order."
        )
    if profile.has_steps:
        parts.append(
            "The evidence describes a process: present it as one numbered step-by-step sequence, "
            "merging steps from all relevant blocks into their natural order."
        )
    if profile.has_table and not profile.has_steps:
        parts.append("Tabular facts in the evidence may be presented as one clean Markdown table.")
    if not (profile.has_code or profile.has_steps or profile.has_table):
        parts.append(
            "The evidence is plain factual prose: answer in short flowing paragraphs; "
            "use bullets only if listing three or more parallel facts genuinely helps."
        )

    if not parts:
        return ""
    return " CONTENT PLAN (derived from the retrieved evidence, follow it): " + " ".join(parts)
