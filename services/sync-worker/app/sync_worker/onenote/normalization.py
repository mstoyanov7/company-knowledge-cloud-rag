from __future__ import annotations

from shared_schemas import SourceDocument

from graph_connectors.onenote.models import OneNotePage, OneNoteSite
from sync_worker.ingestion import compute_content_hash
from sync_worker.onenote.parser import ParsedOneNotePage
from sync_worker.onenote.topic_classifier import OneNoteTopicClassifier


def notebook_acl_tag(notebook_name: str) -> str:
    """Stable ACL tag for a OneNote notebook ("file").

    Access is scoped per notebook: every page inherits the tag derived from its
    notebook name, so the retrieval filter only returns pages from notebooks the
    user holds the matching tag for. The transform matches the notebook entry in
    ``base_tags`` (lowercase, spaces -> hyphens) so the tag an admin assigns to a
    user is predictable from the notebook name, e.g. "TEAM A" -> "team-a".
    """
    return notebook_name.strip().lower().replace(" ", "-") or "unscoped-notebook"


class OneNoteDocumentNormalizer:
    def __init__(self, topic_classifier: OneNoteTopicClassifier | None = None) -> None:
        self.topic_classifier = topic_classifier

    def normalize(
        self,
        *,
        site: OneNoteSite,
        page: OneNotePage,
        parsed_page: ParsedOneNotePage,
        embedding_model: str = "token-hash-v1",
    ) -> SourceDocument:
        source_item_id = f"onenote:{page.id}"
        section_path = f"{page.notebook_name} / {page.section_name}"
        classification = (
            self.topic_classifier.classify(page=page, content_text=parsed_page.text)
            if self.topic_classifier
            else None
        )
        acl_tag = notebook_acl_tag(page.notebook_name)
        base_tags = ["onenote", acl_tag]
        topic_tags = list(classification.tags) if classification else []
        return SourceDocument(
            tenant_id="local-tenant",
            source_system="onenote",
            source_container=f"{site.relative_path}/{page.notebook_name}",
            source_item_id=source_item_id,
            source_url=page.web_url,
            title=page.title,
            file_name=f"{page.title}.one",
            file_extension="one",
            mime_type="text/html",
            section_path=section_path,
            last_modified_utc=page.last_modified_utc,
            acl_tags=[acl_tag],
            content_hash=compute_content_hash(parsed_page.text),
            content_text=parsed_page.text,
            tags=list(dict.fromkeys([*base_tags, *topic_tags])),
            metadata={
                "site_id": site.id,
                "site_name": site.name,
                "notebook_id": page.notebook_id,
                "notebook_name": page.notebook_name,
                "section_id": page.section_id,
                "section_name": page.section_name,
                "page_id": page.id,
                "content_url": page.content_url,
                "page_level": page.page_level,
                "page_order": page.page_order,
                "topic_ids": list(classification.topic_ids) if classification else [],
                "topic_confidence": classification.confidence if classification else {},
                "topic_matched_terms": {
                    topic_id: list(terms)
                    for topic_id, terms in (classification.matched_terms.items() if classification else [])
                },
                "topic_source": "deterministic-config-match" if classification else "unclassified",
                "embedding_model": embedding_model,
                "resource_refs": [
                    {
                        "resource_type": resource.resource_type,
                        "resource_url": resource.resource_url,
                        "name": resource.name,
                        "mime_type": resource.mime_type,
                        "preview_url": resource.preview_url,
                    }
                    for resource in parsed_page.resources
                ],
                "parser_stats": parsed_page.metadata,
                "acl_source": "notebook-scoped",
            },
        )
