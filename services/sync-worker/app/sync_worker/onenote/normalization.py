from __future__ import annotations

from shared_schemas import SourceDocument

from graph_connectors.onenote.models import OneNotePage, OneNoteSite
from sync_worker.ingestion import compute_content_hash
from sync_worker.onenote.parser import ParsedOneNotePage


class OneNoteDocumentNormalizer:
    def normalize(
        self,
        *,
        site: OneNoteSite,
        page: OneNotePage,
        parsed_page: ParsedOneNotePage,
    ) -> SourceDocument:
        source_item_id = f"onenote:{page.id}"
        section_path = f"{page.notebook_name} / {page.section_name}"
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
            acl_tags=["employees"],
            content_hash=compute_content_hash(parsed_page.text),
            content_text=parsed_page.text,
            tags=["onenote", page.notebook_name.lower().replace(" ", "-")],
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
                "acl_source": "restricted-onboarding-default",
            },
        )
