from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata

from shared_schemas import AppSettings, SourceDocument

from rag_api.persistence.app_store import AppDataStore, AppTopicRecord, json_dumps
from rag_api.ports import DocumentMetadataPort

TOPIC_SYNC_ACTOR = "topic-sync"
_DERIVED_SOURCE_FILTERS = ["onenote"]
_DEFAULT_DERIVED_ICON = "notebook-tabs"
_SECTION_ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("benefit",), "gift"),
    (("engineering", "handbook"), "book-open"),
    (("finance", "finances", "procurement"), "wallet-cards"),
    (("internal", "tools", "access"), "key-round"),
    (("onboarding",), "graduation-cap"),
    (("people", "hr", "human resources"), "users-round"),
    (("project", "setup"), "folder-kanban"),
    (("release", "deployment"), "rocket"),
    (("runbook", "troubleshooting", "support"), "life-buoy"),
    (("security", "compliance"), "shield-check"),
)


@dataclass(slots=True)
class _SectionSummary:
    name: str
    acl_tags: set[str] = field(default_factory=set)
    document_count: int = 0


def reconcile_topics_from_sources(
    metadata: DocumentMetadataPort,
    store: AppDataStore,
    settings: AppSettings,
    *,
    prune_stale: bool = True,
) -> list[AppTopicRecord]:
    sections = _sections_from_documents(metadata.list_documents())
    records = store.list_topic_records(enabled_only=False)
    records_by_id = {record.topic_id: record for record in records}
    records_by_section_key = {
        record.section_key: record
        for record in records
        if record.section_key
    }

    current_section_keys = set(sections)
    for section_key, summary in sorted(sections.items(), key=lambda item: item[0].lower()):
        existing = records_by_section_key.get(section_key)
        topic_id = existing.topic_id if existing is not None else _topic_id_for_section(section_key, records_by_id)
        if existing is not None and existing.updated_by_user_id != TOPIC_SYNC_ACTOR:
            continue

        acl_tags = _acl_tags_for_section(summary, settings)
        updated = store.upsert_topic_record(
            topic_id,
            {
                "name": summary.name,
                "description": f"Pages from the {summary.name} section.",
                "icon": _icon_for_section(summary.name),
                "acl_tags_json": json_dumps(acl_tags),
                "source_filters_json": json_dumps(_DERIVED_SOURCE_FILTERS),
                "section_filters_json": json_dumps([summary.name]),
                "retrieval_tags_json": json_dumps([]),
                "suggested_questions_json": json_dumps([]),
                "section_key": section_key,
                "auto_managed": True,
                "enabled": True,
            },
            updated_by_user_id=TOPIC_SYNC_ACTOR,
        )
        records_by_id[updated.topic_id] = updated
        records_by_section_key[section_key] = updated

    if prune_stale:
        stale_topic_ids: list[str] = []
        for record in list(records_by_id.values()):
            if not record.auto_managed or record.section_key in current_section_keys:
                continue
            if record.updated_by_user_id == TOPIC_SYNC_ACTOR:
                # Purely sync-managed topic whose section no longer exists
                # (renamed or removed). Delete it so renamed sections do not
                # leave behind disabled duplicates that clutter the topic list.
                stale_topic_ids.append(record.topic_id)
            else:
                # A human customized this topic; keep their edits but hide it so
                # it does not linger as a filter for a section that is gone.
                store.upsert_topic_record(record.topic_id, {"enabled": False}, updated_by_user_id=TOPIC_SYNC_ACTOR)

        if stale_topic_ids:
            store.delete_topic_records(stale_topic_ids)

    return store.list_topic_records(enabled_only=False)


def _sections_from_documents(documents: list[SourceDocument]) -> dict[str, _SectionSummary]:
    sections: dict[str, _SectionSummary] = {}
    for document in documents:
        section_name = _section_name(document)
        if not section_name:
            continue
        summary = sections.setdefault(section_name, _SectionSummary(name=section_name))
        summary.document_count += 1
        summary.acl_tags.update(_unique_clean_values(document.acl_tags))
    return sections


def _section_name(document: SourceDocument) -> str:
    value = (document.metadata or {}).get("section_name")
    return str(value).strip() if value is not None else ""


def _acl_tags_for_section(summary: _SectionSummary, settings: AppSettings) -> list[str]:
    acl_tags = sorted(summary.acl_tags, key=str.lower)
    return acl_tags or _unique_clean_values(settings.auth_default_acl_tag_list)


def _icon_for_section(section_name: str) -> str:
    normalized = section_name.casefold()
    for terms, icon in _SECTION_ICON_RULES:
        if any(term in normalized for term in terms):
            return icon
    return _DEFAULT_DERIVED_ICON


def _topic_id_for_section(section_key: str, records_by_id: dict[str, AppTopicRecord]) -> str:
    base = f"section-{_slug(section_key)}"
    candidate = _truncate_topic_id(base)
    if _id_available_for_section(candidate, section_key, records_by_id):
        return candidate

    digest = hashlib.sha1(section_key.encode("utf-8")).hexdigest()[:8]
    candidate = _truncate_topic_id(base, suffix=f"-{digest}")
    if _id_available_for_section(candidate, section_key, records_by_id):
        return candidate

    counter = 2
    while True:
        candidate = _truncate_topic_id(base, suffix=f"-{digest}-{counter}")
        if _id_available_for_section(candidate, section_key, records_by_id):
            return candidate
        counter += 1


def _id_available_for_section(topic_id: str, section_key: str, records_by_id: dict[str, AppTopicRecord]) -> bool:
    existing = records_by_id.get(topic_id)
    return existing is None or existing.section_key == section_key


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _truncate_topic_id(base: str, *, suffix: str = "") -> str:
    max_base_length = 120 - len(suffix)
    return f"{base[:max_base_length].rstrip('-')}{suffix}"


def _unique_clean_values(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))
