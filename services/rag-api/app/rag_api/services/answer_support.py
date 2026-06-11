"""Small cross-cutting helpers shared by the answer service and feature modules
(e.g. inventory). Kept here so feature modules can reuse them without importing
the answer service, which would create an import cycle."""

from __future__ import annotations

from datetime import UTC, datetime

from shared_schemas import Citation


def _freshness_delay_ms(citations: list[Citation]) -> int | None:
    if not citations:
        return None
    newest_source_timestamp = max(citation.last_modified_utc.astimezone(UTC) for citation in citations)
    return max(0, int((datetime.now(UTC) - newest_source_timestamp).total_seconds() * 1000))


def _metadata_string(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, dict):
            value = value.get("displayName") or value.get("user", {}).get("displayName")
        if value:
            return str(value).strip()
    return None
