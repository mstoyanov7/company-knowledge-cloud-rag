from __future__ import annotations

from shared_schemas import SourceDocument

from graph_connectors.sharepoint.models import SharePointDrive, SharePointDriveItem, SharePointSite
from sync_worker.ingestion import ExtractedContent, compute_content_hash


class SharePointDocumentNormalizer:
    def normalize(
        self,
        *,
        site: SharePointSite,
        drive: SharePointDrive,
        item: SharePointDriveItem,
        extracted_content: ExtractedContent,
    ) -> SourceDocument:
        section_path = item.parent_path or "/"
        return SourceDocument(
            tenant_id="local-tenant",
            source_system="sharepoint",
            source_container=f"{site.relative_path}/{drive.name}",
            source_item_id=item.id,
            source_url=item.web_url,
            title=item.name,
            file_name=item.file_name,
            file_extension=item.file_extension,
            mime_type=item.mime_type,
            section_path=section_path,
            last_modified_utc=item.last_modified_utc,
            acl_tags=item.acl_tags,
            content_hash=compute_content_hash(extracted_content.text),
            content_text=extracted_content.text,
            tags=["sharepoint", drive.name.lower()],
            metadata={
                "site_id": site.id,
                "site_name": site.name,
                "drive_id": drive.id,
                "drive_name": drive.name,
                "extractor": extracted_content.extractor_name,
                "extractor_metadata": extracted_content.metadata,
                "parent_path": item.parent_path,
                "mime_type": item.mime_type,
                "e_tag": item.e_tag,
                "c_tag": item.c_tag,
            },
        )
