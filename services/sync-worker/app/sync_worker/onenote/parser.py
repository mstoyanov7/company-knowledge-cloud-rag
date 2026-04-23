from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup, NavigableString, Tag


@dataclass(slots=True)
class OneNoteResourceRef:
    resource_type: str
    resource_url: str
    name: str | None = None
    mime_type: str | None = None
    preview_url: str | None = None


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

        cleaned_blocks = [block.strip() for block in blocks if block and block.strip()]
        return ParsedOneNotePage(
            text="\n\n".join(cleaned_blocks).strip(),
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
            text = self._inline_text(node)
            return [text] if text else []

        if node.name == "br":
            return [""]

        if node.name in {"ul", "ol"}:
            return self._render_list(node, indent=indent)

        if node.name == "table":
            return self._render_table(node)

        if node.name == "img":
            label = node.get("alt") or "Embedded image"
            return [f"[Image: {label}]"]

        if node.name == "object":
            label = node.get("data-attachment") or node.get("name") or "Embedded attachment"
            return [f"[Attachment: {label}]"]

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
        return " ".join(part.strip() for part in node.stripped_strings if part.strip())
