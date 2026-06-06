from __future__ import annotations

from datetime import datetime
from textwrap import shorten

from rag_api.ports import DocumentMetadataPort
from rag_api.services.access_scope import AccessScopeResolver
from shared_schemas import (
    AccessScope,
    DocumentDetail,
    DocumentSummary,
    DownloadLink,
    Notebook,
    NotebookPage,
    NotebookSection,
    SourceAttachment,
    SourceDocument,
    UserContext,
)


class DocumentService:
    def __init__(
        self,
        *,
        metadata: DocumentMetadataPort,
        access_scope_resolver: AccessScopeResolver,
    ) -> None:
        self.metadata = metadata
        self.access_scope_resolver = access_scope_resolver

    def list_documents(
        self,
        user_context: UserContext,
        *,
        sort: str = "recently_updated",
        limit: int = 20,
    ) -> list[DocumentSummary]:
        access_scope = self.access_scope_resolver.resolve(user_context, [])
        allowed_documents = self._allowed_documents(access_scope)
        attachment_updates = self._attachment_update_times(access_scope, [document.source_item_id for document in allowed_documents])
        documents = [
            _summary(document, updated_at_utc=_effective_updated_at(document, attachment_updates.get(document.source_item_id)))
            for document in allowed_documents
        ]
        if sort == "recently_updated":
            documents.sort(key=lambda document: document.updated_at_utc or document.last_modified_utc, reverse=True)
        else:
            documents.sort(key=lambda document: document.title.lower())
        return documents[: max(1, min(limit, 100))]

    def get_document_detail(
        self,
        user_context: UserContext,
        *,
        source_item_id: str,
        source_system: str | None = None,
    ) -> DocumentDetail | None:
        source_filters = [source_system] if source_system else []
        access_scope = self.access_scope_resolver.resolve(user_context, source_filters)
        for document in self._allowed_documents(access_scope):
            if document.source_item_id == source_item_id:
                return _detail(document)
        return None

    def list_notebooks(self, user_context: UserContext) -> list[Notebook]:
        access_scope = self.access_scope_resolver.resolve(user_context, [])
        sections_by_key: dict[tuple[str, str], NotebookSection] = {}
        notebooks_by_id: dict[str, Notebook] = {}

        for document in self._allowed_documents(access_scope):
            if document.metadata.get("document_kind") == "attachment":
                continue
            notebook_id = str(document.metadata.get("notebook_id") or _notebook_name(document) or "notebook")
            notebook_title = str(document.metadata.get("notebook_name") or _notebook_name(document) or "Notebook")
            section_id = str(document.metadata.get("section_id") or _section_name(document) or "section")
            section_title = str(document.metadata.get("section_name") or _section_name(document) or "Pages")

            notebook = notebooks_by_id.setdefault(
                notebook_id,
                Notebook(
                    id=notebook_id,
                    title=notebook_title,
                    source_url=_metadata_url(document, "notebook_url") or document.source_url,
                    sections=[],
                ),
            )
            section_key = (notebook_id, section_id)
            section = sections_by_key.get(section_key)
            if section is None:
                section = NotebookSection(
                    id=section_id,
                    title=section_title,
                    source_url=_metadata_url(document, "section_url"),
                    section_path=document.section_path,
                    pages=[],
                )
                sections_by_key[section_key] = section
                notebook.sections.append(section)
            section.pages.append(_page(document))

        notebooks = list(notebooks_by_id.values())
        for notebook in notebooks:
            notebook.sections.sort(key=lambda section: section.title.lower())
            for section in notebook.sections:
                section.pages.sort(key=lambda page: page.title.lower())
        notebooks.sort(key=lambda notebook: notebook.title.lower())
        return notebooks

    def get_attachment_for_download(
        self,
        user_context: UserContext,
        *,
        download_id: str,
    ) -> SourceAttachment | None:
        access_scope = self.access_scope_resolver.resolve(user_context, [])
        attachment = self.metadata.get_attachment(download_id)
        if attachment is None:
            return None
        if not _attachment_allowed(attachment, access_scope):
            return None
        return attachment

    def list_downloads_for_sources(
        self,
        user_context: UserContext,
        source_item_ids: list[str],
    ) -> list[DownloadLink]:
        access_scope = self.access_scope_resolver.resolve(user_context, [])
        attachments = self.metadata.list_attachments(source_item_ids)
        return [_download_link(attachment) for attachment in attachments if _attachment_allowed(attachment, access_scope)]

    def _allowed_documents(self, access_scope: AccessScope) -> list[SourceDocument]:
        allowed_acl_tags = set(access_scope.allowed_acl_tags)
        allowed: list[SourceDocument] = []
        for document in self.metadata.list_documents():
            if document.tenant_id != access_scope.tenant_id:
                continue
            if access_scope.source_filters and document.source_system not in access_scope.source_filters:
                continue
            document_acl_tags = set(document.acl_tags)
            if document_acl_tags and not document_acl_tags.intersection(allowed_acl_tags):
                continue
            allowed.append(document)
        return allowed

    def _attachment_update_times(
        self,
        access_scope: AccessScope,
        source_item_ids: list[str],
    ) -> dict[str, datetime]:
        if not source_item_ids:
            return {}
        updates: dict[str, datetime] = {}
        for attachment in self.metadata.list_attachments(source_item_ids):
            if not _attachment_allowed(attachment, access_scope):
                continue
            timestamp = attachment.updated_at_utc or attachment.last_modified_utc
            existing = updates.get(attachment.parent_source_item_id)
            if existing is None or timestamp > existing:
                updates[attachment.parent_source_item_id] = timestamp
        return updates


def _summary(document: SourceDocument, *, updated_at_utc=None) -> DocumentSummary:
    return DocumentSummary(
        id=str(document.metadata.get("page_id") or document.source_item_id),
        title=document.title,
        section_path=document.section_path,
        source_url=document.source_url,
        source_item_id=document.source_item_id,
        source_system=document.source_system,
        source_container=document.source_container,
        last_modified_utc=document.last_modified_utc,
        updated_at_utc=updated_at_utc or document.updated_at_utc or document.last_modified_utc,
        snippet=shorten(document.content_text, width=220, placeholder="...") if document.content_text else None,
        last_edited_by=_last_edited_by(document),
        client_url=_client_url(document),
        metadata=document.metadata,
    )


def _detail(document: SourceDocument) -> DocumentDetail:
    return DocumentDetail(
        **_summary(document, updated_at_utc=_effective_updated_at(document)).model_dump(),
        content_text=document.content_text,
    )


def _page(document: SourceDocument) -> NotebookPage:
    summary = _summary(document, updated_at_utc=_effective_updated_at(document))
    return NotebookPage(**summary.model_dump())


def _effective_updated_at(document: SourceDocument, attachment_updated_at=None):
    candidates = [document.last_modified_utc]
    if document.updated_at_utc is not None:
        candidates.append(document.updated_at_utc)
    if attachment_updated_at is not None:
        candidates.append(attachment_updated_at)
    return max(candidates)


def _notebook_name(document: SourceDocument) -> str:
    if document.section_path and "/" in document.section_path:
        return document.section_path.split("/", maxsplit=1)[0].strip()
    return document.source_container.rsplit("/", maxsplit=1)[-1] if document.source_container else "Notebook"


def _section_name(document: SourceDocument) -> str:
    if document.section_path and "/" in document.section_path:
        return document.section_path.rsplit("/", maxsplit=1)[-1].strip()
    return document.section_path or "Pages"


def _last_edited_by(document: SourceDocument) -> str | None:
    value = (
        document.metadata.get("last_edited_by")
        or document.metadata.get("lastEditedBy")
        or document.metadata.get("last_modified_by")
        or document.metadata.get("lastModifiedBy")
    )
    if isinstance(value, dict):
        value = value.get("displayName") or value.get("user", {}).get("displayName")
    return str(value).strip() if value else None


def _client_url(document: SourceDocument) -> str | None:
    value = (
        document.metadata.get("client_url")
        or document.metadata.get("oneNoteClientUrl")
        or document.metadata.get("onenote_client_url")
    )
    return str(value).strip() if value else None


def _metadata_url(document: SourceDocument, key: str) -> str | None:
    value = document.metadata.get(key)
    return str(value).strip() if value else None


def _attachment_allowed(attachment: SourceAttachment, access_scope: AccessScope) -> bool:
    if attachment.tenant_id != access_scope.tenant_id:
        return False
    attachment_acl_tags = set(attachment.acl_tags)
    return not attachment_acl_tags or bool(attachment_acl_tags.intersection(access_scope.allowed_acl_tags))


def _download_link(attachment: SourceAttachment) -> DownloadLink:
    download_url = (
        f"/api/v1/attachments/{attachment.download_id}/download"
        if attachment.storage_path
        else attachment.resource_url
    )
    return DownloadLink(
        download_id=attachment.download_id,
        file_name=attachment.file_name,
        mime_type=attachment.mime_type,
        file_extension=attachment.file_extension,
        size_bytes=attachment.size_bytes,
        readable=attachment.readable,
        parent_source_item_id=attachment.parent_source_item_id,
        parent_title=attachment.parent_title,
        download_url=download_url,
        indexed_source_item_id=attachment.indexed_source_item_id,
    )

