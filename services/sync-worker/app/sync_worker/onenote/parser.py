from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Protocol
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from sync_worker.ingestion import DOWNLOADABLE_ATTACHMENT_EXTENSIONS


@dataclass(slots=True)
class OneNoteResourceRef:
    resource_type: str
    resource_url: str
    name: str | None = None
    mime_type: str | None = None
    preview_url: str | None = None
    resource_origin: str = "embedded"


@dataclass(slots=True)
class ParsedOneNotePage:
    text: str
    resources: list[OneNoteResourceRef] = field(default_factory=list)
    metadata: dict[str, int] = field(default_factory=dict)


class OneNoteResourceHook(Protocol):
    def handle_resources(self, page_id: str, resources: list[OneNoteResourceRef]) -> None:
        ...


class NullOneNoteResourceHook:
    def handle_resources(self, page_id: str, resources: list[OneNoteResourceRef]) -> None:
        return None


class OneNoteHtmlParser:
    def parse(self, html: str) -> ParsedOneNotePage:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.body or soup
        resources = self._collect_resources(body)
        blocks: list[str] = []
        for child in body.children:
            blocks.extend(self._render_block(child, indent=0))

        cleaned_blocks = [block for block in (_clean_block(block) for block in blocks) if block]
        grouped_blocks = _group_command_blocks(cleaned_blocks)
        text = normalize_parsed_text("\n\n".join(grouped_blocks))
        return ParsedOneNotePage(
            text=text,
            resources=resources,
            metadata={
                "heading_count": len(body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])),
                "list_count": len(body.find_all(["ul", "ol"])),
                "table_count": len(body.find_all("table")),
                "resource_count": len(resources),
            },
        )

    def _collect_resources(self, body: Tag) -> list[OneNoteResourceRef]:
        resources: list[OneNoteResourceRef] = []
        for image in body.find_all("img"):
            resource_url = image.get("data-fullres-src") or image.get("src")
            if resource_url:
                resources.append(
                    OneNoteResourceRef(
                        resource_type="image",
                        resource_url=resource_url,
                        preview_url=image.get("src"),
                        name=image.get("alt"),
                    )
                )
        for obj in body.find_all("object"):
            resource_url = obj.get("data")
            if resource_url:
                resources.append(
                    OneNoteResourceRef(
                        resource_type="attachment",
                        resource_url=resource_url,
                        name=obj.get("data-attachment") or obj.get("name"),
                        mime_type=obj.get("type"),
                        resource_origin="embedded",
                    )
                )
        for link in body.find_all("a"):
            href = link.get("href")
            if href and _is_downloadable_href(href):
                resources.append(
                    OneNoteResourceRef(
                        resource_type="attachment",
                        resource_url=href,
                        name=_link_resource_name(link, href),
                        resource_origin="link",
                    )
                )
        return resources

    def _render_block(self, node: Tag | NavigableString, *, indent: int) -> list[str]:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            return [text] if text else []

        if not isinstance(node, Tag):
            return []

        if node.name in {"script", "style", "meta", "head"}:
            return []

        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(node.name[1])
            return [f"{'#' * level} {self._inline_text(node)}"]

        if node.name == "p":
            return self._paragraph_blocks(node)

        if node.name == "br":
            return [""]

        if node.name in {"ul", "ol"}:
            lines = self._render_list(node, indent=indent)
            return ["\n".join(lines)] if lines else []

        if node.name == "table":
            lines = self._render_table(node)
            return ["\n".join(lines)] if lines else []

        if node.name == "img":
            label = _clean_resource_label(node.get("alt"))
            return [f"[Image: {label}]"] if label else []

        if node.name == "object":
            label = _clean_resource_label(node.get("data-attachment") or node.get("name"))
            return [f"[Attachment: {label}]"] if label else []

        if node.name == "a":
            text = self._inline_text(node)
            href = node.get("href")
            if href and _is_downloadable_href(href):
                name = _link_resource_name(node, href)
                if text and text != href:
                    return [f"{text} ({href})"]
                return [href or name]
            return [text] if text else []

        blocks: list[str] = []
        for child in node.children:
            blocks.extend(self._render_block(child, indent=indent))
        return blocks

    def _render_list(self, node: Tag, *, indent: int) -> list[str]:
        lines: list[str] = []
        is_ordered = node.name == "ol"
        index = 1
        for child in node.children:
            if not isinstance(child, Tag) or child.name != "li":
                continue
            prefix = f"{index}." if is_ordered else "-"
            own_text_parts: list[str] = []
            nested_blocks: list[str] = []
            for item_child in child.children:
                if isinstance(item_child, NavigableString):
                    text = str(item_child).strip()
                    if text:
                        own_text_parts.append(text)
                elif isinstance(item_child, Tag) and item_child.name in {"ul", "ol"}:
                    nested_blocks.extend(self._render_list(item_child, indent=indent + 2))
                else:
                    text = self._inline_text(item_child)
                    if text:
                        own_text_parts.append(text)
            if own_text_parts:
                lines.append(f"{' ' * indent}{prefix} {' '.join(own_text_parts).strip()}")
            lines.extend(nested_blocks)
            index += 1
        return lines

    def _render_table(self, node: Tag) -> list[str]:
        rows: list[list[str]] = []
        for table_row in node.find_all("tr"):
            cells = [self._inline_text(cell) for cell in table_row.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            return []
        lines = [f"| {' | '.join(rows[0])} |"]
        if len(rows) > 1:
            lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
            lines.extend(f"| {' | '.join(row)} |" for row in rows[1:])
        return lines

    def _inline_text(self, node: Tag) -> str:
        return _clean_text_block(" ".join(part.strip() for part in node.stripped_strings if part.strip()))

    def _paragraph_blocks(self, node: Tag) -> list[str]:
        blocks: list[str] = []
        parts: list[str] = []

        def flush() -> None:
            text = _clean_text_block(" ".join(parts))
            if text:
                blocks.append(text)
            parts.clear()

        def collect(child: Tag | NavigableString) -> None:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    parts.append(text)
                return
            if not isinstance(child, Tag):
                return
            if child.name == "br":
                flush()
                return
            if child.name in {"script", "style", "meta", "head"}:
                return
            for nested in child.children:
                collect(nested)

        for child in node.children:
            collect(child)
        flush()
        return blocks


_INVISIBLE_ARTIFACTS = {
    "\ufffc",  # object replacement character
    "\ufffd",  # replacement character from bad decoding
    "\u200b",
    "\u200c",
    "\u200d",
    "\ufeff",
}

_EMPTY_RESOURCE_LABELS = {
    "",
    "embedded attachment",
    "embedded image",
    "image",
    "img",
    "object",
    "obj",
    "attachment",
}


# Lines made up only of stray punctuation or a single isolated letter are
# extraction noise (the "random single letters" artifact) and are dropped.
_GARBAGE_LINE = re.compile(r"^(?:[A-Za-z]|[^\w\s])$")
# Shell/command lines that should be grouped into fenced code blocks.
_COMMAND_PREFIX = re.compile(
    r"^(?:sudo|apt|apt-get|flutter|dart|git|cd|export|set|make|cmake|ninja|"
    r"pip|pip3|python|python3|npm|yarn|pnpm|node|docker|kubectl|helm|bash|sh|"
    r"curl|wget|ssh|scp|cp|mv|mkdir|rm|chmod|chown|systemctl|source|\./)"
    r"(?:\s|$)",
    re.IGNORECASE,
)
_COMMAND_ASSIGNMENT = re.compile(r"^[A-Z][A-Z0-9_]+=\S")

# Splits a flattened run of shell commands (multiple commands joined on one line)
# back into one command per line. Only a curated set of command starters that
# are rarely used as arguments are used as split points, to avoid breaking a
# single command's own arguments (e.g. "apt install -y make gcc").
# Note: "./" is intentionally NOT a split point - "VAR=value ./prog" is one
# command (an env-prefixed executable), not two.
_COMMAND_RUN_SPLIT = re.compile(
    r"(?<=\S)\s+(?=(?:git|cd|cmake|flutter|dart|docker|kubectl|helm|npm|yarn|pnpm|sudo|apt-get)\b)"
)
# Package-install lines list packages as bare words (e.g. "apt install -y cmake
# make gcc"); those words must not be mistaken for new commands and split.
_INSTALL_LIST = re.compile(
    r"\b(?:apt|apt-get|pip|pip3|npm|yarn|pnpm|apk|dnf|yum|brew|gem|cargo)\s+(?:install|add)\b",
    re.IGNORECASE,
)


def _clean_text_block(value: str) -> str:
    """Clean a single line: drop artifacts and collapse runs of whitespace."""

    cleaned = value
    for artifact in _INVISIBLE_ARTIFACTS:
        cleaned = cleaned.replace(artifact, " ")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"(?<![A-Za-z0-9_.-])OBJ(?![A-Za-z0-9_.-])", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _clean_block(block: str) -> str:
    """Clean a structural block while preserving its internal line breaks."""

    lines = [_clean_text_block(line) for line in block.split("\n")]
    lines = [line for line in lines if line and not _GARBAGE_LINE.match(line)]
    return "\n".join(lines).strip()


def _looks_like_command(block: str) -> bool:
    if "\n" in block:
        return False
    stripped = block.strip()
    if not stripped or stripped.startswith(("#", "-", "*", "|", ">")):
        return False
    if re.match(r"^\d+[.)]\s", stripped):  # numbered list item
        return False
    if re.search(r"\s/\s", stripped):  # breadcrumb like "Flutter / Linux / EGL"
        return False
    return bool(_COMMAND_PREFIX.match(stripped) or _COMMAND_ASSIGNMENT.match(stripped))


def _split_command_line(line: str) -> list[str]:
    """Split a line that runs several commands together into one per line.

    Package-install lines (``apt install ...``, ``pip install ...``) are left
    intact so package names are not mistaken for separate commands.
    """

    stripped = line.strip()
    if _INSTALL_LIST.search(stripped):
        return [stripped]
    parts = [part.strip() for part in _COMMAND_RUN_SPLIT.split(stripped)]
    return [part for part in parts if part] or [stripped]


def _group_command_blocks(blocks: list[str]) -> list[str]:
    """Merge consecutive command lines into a single fenced ```bash block."""

    grouped: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            grouped.append("```bash\n" + "\n".join(buffer) + "\n```")
            buffer.clear()

    for block in blocks:
        if _looks_like_command(block):
            buffer.extend(_split_command_line(block.strip()))
        else:
            flush()
            grouped.append(block)
    flush()
    return grouped


def normalize_parsed_text(text: str) -> str:
    """Final normalization pass applied before hashing/indexing.

    Collapses excess blank lines and trailing spaces while leaving fenced code
    blocks, tables, and lists intact.
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _clean_resource_label(value: str | None) -> str:
    cleaned = _clean_text_block(value or "")
    if cleaned.lower() in _EMPTY_RESOURCE_LABELS:
        return ""
    return cleaned


def _is_downloadable_href(href: str) -> bool:
    parsed = urlparse(href)
    path = unquote(parsed.path or href)
    extension = PurePosixPath(path).suffix.lower()
    return extension in DOWNLOADABLE_ATTACHMENT_EXTENSIONS


def _link_resource_name(link: Tag, href: str) -> str:
    text = _clean_text_block(" ".join(part.strip() for part in link.stripped_strings if part.strip()))
    if text and text.lower() not in _EMPTY_RESOURCE_LABELS:
        return text
    parsed = urlparse(href)
    name = PurePosixPath(unquote(parsed.path or href)).name
    return name or href
