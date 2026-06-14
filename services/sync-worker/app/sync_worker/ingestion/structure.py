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

# Sections, in canonical order, that make up a setup procedure. "steps" and
# "commands" are inferred from a section's *content shape* (numbered steps /
# command lines), so a procedure is recognized even when the author titled the
# section with words the keyword table does not know ("Setup Process", "Commands").
PROCEDURE_KINDS: tuple[str, ...] = (
    "prerequisites",
    "steps",
    "install",
    "configuration",
    "run",
    "commands",
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


# A line that is (or starts with) a shell command. Tolerates a leading bullet or
# number marker so a "Commands" list written as bullets is still recognized.
_COMMAND_LINE = re.compile(
    r"^\s*(?:[-*]\s+|\d+[.)]\s+)?"
    r"(?:\$\s|>\s|#!|sudo\s|pip3?\s+install|pipx\s|npm\s|yarn\s|pnpm\s|"
    r"winget\s|brew\s|apt(?:-get)?\s|dnf\s|yum\s|docker(?:\s+compose)?\s|"
    r"kubectl\s|helm\s|git\s+(?:clone|checkout|pull|push|init|submodule)\b|"
    r"curl\s|wget\s|make\s|cmake\s|python3?\s|node\s|go\s+(?:run|build|get|test)\b|"
    r"cargo\s|alembic\s|uvicorn\s|gunicorn\s|flutter\s|dotnet\s|mvn\s|gradle\s|"
    r"terraform\s|ansible(?:-playbook)?\s|vagrant\s|nw\s|psql\s|mysql\s|redis-cli\s|"
    r"export\s+[A-Z_]+=|[A-Z][A-Z0-9_]{2,}=\S)",
    re.IGNORECASE,
)
# A line that is an ordered step: "1. ...", "2) ...", "Step 3 ...", or an
# imperative bullet in a sequence ("- First ...", "- Then ...").
_STEP_LINE = re.compile(
    r"^\s*(?:\d+[.)]\s+\S|step\s+\d+\b|[-*]\s+(?:first|then|next|after that|afterwards|finally)\b)",
    re.IGNORECASE,
)


def _has_code_block(body: str) -> bool:
    return body.startswith("```") or "\n```" in f"\n{body}"


def _count_lines(body: str, pattern: re.Pattern[str]) -> int:
    return sum(1 for line in body.splitlines() if pattern.match(line))


def _body_kind(body: str) -> str | None:
    """Classify a section by the shape of its body, independent of its heading.

    This is what makes classification robust to writing style: a section is
    procedural because it *contains* commands or numbered steps, not because the
    author used a keyword like "Install" or "Setup" in the heading.
    """
    if _has_code_block(body) or _count_lines(body, _COMMAND_LINE) >= 2:
        return "commands"
    if _count_lines(body, _STEP_LINE) >= 2:
        return "steps"
    if body.startswith("|") or "\n|" in body:
        return "table"
    return None


def classify_section(heading_text: str, body: str) -> str:
    # Metadata-shaped bodies (Repository/Owner/Summary lines, breadcrumbs) win
    # even under a title heading that happens to contain words like "Setup".
    if _looks_like_metadata(body):
        return "metadata"
    # A recognized heading keyword is the most precise signal when the author
    # uses one, so it is honored first.
    if heading_text:
        for pattern, kind in _KIND_PATTERNS:
            if pattern.search(heading_text):
                return kind
    # Otherwise fall back to the body's content shape, so a section whose heading
    # uses no known keyword ("Setup Process", "Spin it up locally", "Commands")
    # is still classified by what it actually contains.
    body_kind = _body_kind(body)
    if body_kind is not None:
        return body_kind
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
