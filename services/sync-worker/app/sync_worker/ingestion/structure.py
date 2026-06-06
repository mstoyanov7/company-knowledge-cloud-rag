"""Structure-aware parsing of clean Markdown-like OneNote page text.

Splits a page into heading-delimited sections without ever breaking inside a
word, fenced code block, table row, or list item. Used by the chunker so that
procedure sections (Install / Configuration / Run / Verification) stay together
and are classified with a ``chunk_kind``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

_HEADING = re.compile(r"^#{1,6}\s+\S")
_FENCE = re.compile(r"^```")

# Heading keyword -> chunk_kind. Checked in order; first match wins.
_KIND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(overview|introduction|about|purpose)", re.IGNORECASE), "overview"),
    (re.compile(r"\b(prerequisite|requirement|dependenc)", re.IGNORECASE), "prerequisites"),
    (re.compile(r"\b(install|getting started)", re.IGNORECASE), "install"),
    (re.compile(r"\b(config|setting|environment)", re.IGNORECASE), "configuration"),
    (re.compile(r"\b(run|launch|start|build|deploy|usage|execute)", re.IGNORECASE), "run"),
    (re.compile(r"\b(verif|validat|smoke|sanity|confirm|acceptance)", re.IGNORECASE), "verification"),
    (re.compile(r"\b(troubleshoot|problem|error|issue|faq|debug)", re.IGNORECASE), "troubleshooting"),
    (re.compile(r"\b(checklist|completion|sign)", re.IGNORECASE), "checklist"),
    (re.compile(r"\b(repository structure|structure|layout)", re.IGNORECASE), "reference"),
)

# Sections, in canonical order, that make up a setup procedure.
PROCEDURE_KINDS: tuple[str, ...] = (
    "prerequisites",
    "install",
    "configuration",
    "run",
    "verification",
)


@dataclass(slots=True)
class Section:
    heading: str | None
    blocks: list[str] = field(default_factory=list)
    kind: str = "section"

    @property
    def heading_text(self) -> str:
        return (self.heading or "").lstrip("#").strip()

    @property
    def body(self) -> str:
        return "\n\n".join(self.blocks).strip()

    @property
    def text(self) -> str:
        parts = [self.heading] if self.heading else []
        parts.extend(self.blocks)
        return "\n\n".join(part for part in parts if part).strip()

    def __len__(self) -> int:
        return len(self.text)


def split_blocks(text: str) -> list[str]:
    """Split text into structural blocks, keeping fenced code blocks atomic."""

    blocks: list[str] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        block = "\n".join(current).strip("\n")
        if block.strip():
            blocks.append(block)
        current.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line.strip()):
            current.append(line)
            if in_fence:  # closing fence ends the code block
                in_fence = False
                flush()
            else:
                in_fence = True
            continue
        if in_fence:
            current.append(line)
            continue
        if not line.strip():
            flush()
            continue
        current.append(line)
    flush()
    return blocks


_METADATA_LABEL = re.compile(
    r"^(section|repository|owner|author|summary|tags?|status|page metadata|"
    r"last edited|last modified|notebook)\s*:",
    re.IGNORECASE,
)


def _looks_like_metadata(body: str) -> bool:
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    meta_lines = sum(
        1 for line in lines if _METADATA_LABEL.match(line) or " / " in line or re.search(r"\s-\s\d+\s", line)
    )
    return meta_lines / len(lines) >= 0.6


def classify_section(heading_text: str, body: str) -> str:
    # Metadata-shaped bodies (Repository/Owner/Summary lines, breadcrumbs) win
    # even under a title heading that happens to contain words like "Setup".
    if _looks_like_metadata(body):
        return "metadata"
    if heading_text:
        for pattern, kind in _KIND_PATTERNS:
            if pattern.search(heading_text):
                return kind
    if "\n```" in f"\n{body}" or body.startswith("```"):
        return "commands"
    if body.startswith("|") or "\n|" in body:
        return "table"
    return "section"


def parse_sections(text: str) -> list[Section]:
    """Group blocks into heading-delimited sections."""

    blocks = split_blocks(text)
    sections: list[Section] = []
    current = Section(heading=None)

    for block in blocks:
        if _HEADING.match(block) and "\n" not in block:
            if current.heading is not None or current.blocks:
                sections.append(current)
            current = Section(heading=block)
        else:
            current.blocks.append(block)
    if current.heading is not None or current.blocks:
        sections.append(current)

    for section in sections:
        if section.heading is None:
            # Leading content before the first heading is page metadata.
            section.kind = "metadata"
        else:
            section.kind = classify_section(section.heading_text, section.body)
    return sections
