from __future__ import annotations

from datetime import UTC, datetime

from shared_schemas import AppSettings, OneNoteCheckpoint, SourceDocument

from graph_connectors.onenote.connector import OneNoteConnector
from graph_connectors.onenote.client import MockOneNoteGraphClient
from graph_connectors.onenote.models import OneNoteNotebook, OneNotePage, OneNoteSection, OneNoteSite
from sync_worker.ingestion import DeterministicEmbedder, TextChunker
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer
from sync_worker.onenote.parser import NullOneNoteResourceHook, OneNoteHtmlParser
from sync_worker.onenote.service import OneNoteSyncService


class FakeOneNoteGraphClient:
    def __init__(
        self,
        *,
        inventory_pages: list[OneNotePage],
        incremental_pages: list[OneNotePage] | None = None,
        content_by_url: dict[str, str],
    ) -> None:
        self.inventory_pages = inventory_pages
        self.incremental_pages = incremental_pages if incremental_pages is not None else inventory_pages
        self.content_by_url = content_by_url
        self.site = OneNoteSite(
            id="site-1",
            name="Onboarding",
            web_url="https://contoso.sharepoint.com/sites/onboarding",
            hostname="contoso.sharepoint.com",
            relative_path="sites/onboarding",
        )
        self.notebooks = [
            OneNoteNotebook(
                id="notebook-1",
                display_name="Team Notebook",
                web_url="https://contoso.sharepoint.com/sites/onboarding/TeamNotebook",
            )
        ]
        self.sections = [
            OneNoteSection(
                id="section-1",
                display_name="Orientation",
                notebook_id="notebook-1",
                notebook_name="Team Notebook",
                web_url="https://contoso.sharepoint.com/sites/onboarding/Orientation",
            )
        ]

    def resolve_site(self) -> OneNoteSite:
        return self.site

    def list_notebooks(self, site_id: str) -> list[OneNoteNotebook]:
        return list(self.notebooks)

    def list_sections(self, site_id: str) -> list[OneNoteSection]:
        return list(self.sections)

    def list_pages(self, site_id: str, *, modified_since=None, next_url=None) -> tuple[list[OneNotePage], str | None]:
        if next_url is not None:
            return [], None
        pages = self.incremental_pages if modified_since is not None else self.inventory_pages
        return list(pages), None

    def get_page_content(self, content_url: str) -> str:
        return self.content_by_url[content_url]


class InMemoryMetadataStore:
    def __init__(self) -> None:
        self.onenote_checkpoints: dict[str, OneNoteCheckpoint] = {}
        self.documents: dict[str, SourceDocument] = {}
        self.deleted_items: list[str] = []
        self.chunks: dict[str, list] = {}

    def ensure_schema(self) -> None:
        return None

    def get_checkpoint(self, scope_key: str):
        return None

    def upsert_checkpoint(self, checkpoint):
        return checkpoint

    def get_onenote_checkpoint(self, scope_key: str) -> OneNoteCheckpoint | None:
        return self.onenote_checkpoints.get(scope_key)

    def upsert_onenote_checkpoint(self, checkpoint: OneNoteCheckpoint) -> OneNoteCheckpoint:
        self.onenote_checkpoints[checkpoint.scope_key] = checkpoint
        return checkpoint

    def get_source_document(self, source_item_id: str) -> SourceDocument | None:
        return self.documents.get(source_item_id)

    def upsert_source_document(self, scope_key: str, document: SourceDocument) -> None:
        self.documents[document.source_item_id] = document

    def mark_source_deleted(self, scope_key: str, source_item_id: str, deleted_at_utc=None) -> None:
        self.deleted_items.append(source_item_id)
        self.documents.pop(source_item_id, None)
        self.chunks.pop(source_item_id, None)

    def replace_chunks(self, scope_key: str, source_item_id: str, chunks: list) -> None:
        self.chunks[source_item_id] = chunks

    def list_active_source_documents(self, scope_key: str, source_system: str) -> list[SourceDocument]:
        return [document for document in self.documents.values() if document.source_system == source_system]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.upserts: dict[str, list[list[float]]] = {}
        self.deleted_source_item_ids: list[str] = []

    def ensure_collection(self) -> None:
        return None

    def upsert_chunks(self, chunks, embeddings) -> None:
        if chunks:
            self.upserts[chunks[0].source_item_id] = embeddings

    def delete_chunks_for_source_item(self, source_item_id: str) -> None:
        self.deleted_source_item_ids.append(source_item_id)


def make_page(
    page_id: str,
    *,
    section_name: str = "Orientation",
    last_modified: datetime | None = None,
    title: str = "Welcome checklist",
) -> OneNotePage:
    return OneNotePage(
        id=page_id,
        title=title,
        content_url=f"mock://onenote/{page_id}",
        web_url=f"https://contoso.sharepoint.com/sites/onboarding/{page_id}",
        created_utc=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        last_modified_utc=last_modified or datetime(2026, 4, 24, 9, 0, tzinfo=UTC),
        notebook_id="notebook-1",
        notebook_name="Team Notebook",
        section_id="section-1" if section_name == "Orientation" else "section-2",
        section_name=section_name,
        page_level=0,
        page_order=0,
    )


def build_service(fake_client: FakeOneNoteGraphClient) -> tuple[OneNoteSyncService, InMemoryMetadataStore, InMemoryVectorStore]:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="mock",
        graph_onenote_site_hostname="contoso.sharepoint.com",
        graph_onenote_site_scope="sites/onboarding",
        graph_onenote_notebook_scope="Team Notebook",
        onenote_chunk_size_chars=80,
        onenote_chunk_overlap_chars=10,
    )
    connector = OneNoteConnector(settings, client=fake_client)
    metadata_store = InMemoryMetadataStore()
    vector_store = InMemoryVectorStore()
    service = OneNoteSyncService(
        settings=settings,
        connector=connector,
        parser=OneNoteHtmlParser(),
        normalizer=OneNoteDocumentNormalizer(),
        chunker=TextChunker(
            settings,
            chunk_size_chars=settings.onenote_chunk_size_chars,
            chunk_overlap_chars=settings.onenote_chunk_overlap_chars,
        ),
        embedder=DeterministicEmbedder(settings),
        metadata_store=metadata_store,
        vector_store=vector_store,
        resource_hook=NullOneNoteResourceHook(),
    )
    return service, metadata_store, vector_store


def test_onenote_parser_preserves_headings_lists_tables_and_resources() -> None:
    parser = OneNoteHtmlParser()
    parsed = parser.parse(
        """
        <html><body>
        <h1>Title</h1>
        <p>Paragraph text.</p>
        <ul><li>First bullet</li><li>Second bullet</li></ul>
        <table><tr><th>Owner</th><th>ETA</th></tr><tr><td>HR</td><td>Day 1</td></tr></table>
        <img src="https://graph.microsoft.com/v1.0/resources/image-1/$value" alt="Diagram" />
        <object data="https://graph.microsoft.com/v1.0/resources/file-1/$value" data-attachment="guide.pdf" type="application/pdf"></object>
        </body></html>
        """
    )

    assert "# Title" in parsed.text
    assert "- First bullet" in parsed.text
    assert "| Owner | ETA |" in parsed.text
    assert "[Image: Diagram]" in parsed.text
    assert "[Attachment: guide.pdf]" in parsed.text
    assert len(parsed.resources) == 2
    assert parsed.metadata["heading_count"] == 1


def test_mock_onenote_client_uses_all_notebooks_when_scope_is_blank() -> None:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="mock",
        graph_onenote_site_hostname="contoso.sharepoint.com",
        graph_onenote_site_scope="sites/onboarding",
        graph_onenote_notebook_scope="",
    )

    client = MockOneNoteGraphClient(settings)

    notebooks = client.list_notebooks("mock-onenote-site")
    sections = client.list_sections("mock-onenote-site")
    pages, _ = client.list_pages("mock-onenote-site")

    assert {notebook.display_name for notebook in notebooks} == {"Team Notebook", "Engineering Notebook"}
    assert {section.display_name for section in sections} == {"Orientation", "Tooling"}
    assert {page.notebook_name for page in pages} == {"Team Notebook", "Engineering Notebook"}


def test_onenote_bootstrap_persists_checkpoint_and_chunks() -> None:
    page = make_page("page-1")
    service, metadata_store, vector_store = build_service(
        FakeOneNoteGraphClient(
            inventory_pages=[page],
            content_by_url={
                page.content_url: "<html><body><h1>Welcome</h1><p>Set up your laptop and VPN.</p></body></html>"
            },
        )
    )

    report = service.bootstrap()

    assert report.items_changed == 1
    assert report.checkpoint is not None
    assert report.checkpoint.last_modified_cursor_utc == page.last_modified_utc
    assert "onenote:page-1" in metadata_store.documents
    assert "onenote:page-1" in metadata_store.chunks
    assert "onenote:page-1" in vector_store.upserts


def test_onenote_incremental_skips_unchanged_and_updates_cursor() -> None:
    page = make_page("page-1", last_modified=datetime(2026, 4, 24, 9, 0, tzinfo=UTC))
    bootstrap_client = FakeOneNoteGraphClient(
        inventory_pages=[page],
        content_by_url={page.content_url: "<html><body><p>Same page content.</p></body></html>"},
    )
    service, metadata_store, _ = build_service(bootstrap_client)
    service.bootstrap()

    updated_page = page.model_copy(update={"last_modified_utc": datetime(2026, 4, 24, 10, 0, tzinfo=UTC)})
    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=[updated_page],
        incremental_pages=[updated_page],
        content_by_url={updated_page.content_url: "<html><body><p>Same page content.</p></body></html>"},
    )

    report = service.incremental()

    assert report.items_skipped == 1
    assert metadata_store.get_onenote_checkpoint(service.settings.onenote_scope_key).last_modified_cursor_utc == updated_page.last_modified_utc


def test_onenote_reconciliation_marks_deleted_pages_and_updates_moved_pages() -> None:
    original_page = make_page("page-1")
    service, metadata_store, vector_store = build_service(
        FakeOneNoteGraphClient(
            inventory_pages=[original_page],
            content_by_url={original_page.content_url: "<html><body><p>Original content.</p></body></html>"},
        )
    )
    service.bootstrap()

    moved_page = make_page("page-1", section_name="Moved Section")
    deleted_page = make_page("page-2")
    metadata_store.documents["onenote:page-2"] = SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/onboarding/Team Notebook",
        source_item_id="onenote:page-2",
        source_url=deleted_page.web_url,
        title=deleted_page.title,
        file_name=f"{deleted_page.title}.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Team Notebook / Orientation",
        last_modified_utc=deleted_page.last_modified_utc,
        acl_tags=[],
        content_hash="old-hash",
        content_text="deleted page",
        tags=["onenote"],
        metadata={"page_id": deleted_page.id, "section_id": deleted_page.section_id, "notebook_id": deleted_page.notebook_id},
    )
    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=[moved_page],
        incremental_pages=[],
        content_by_url={moved_page.content_url: "<html><body><p>Original content.</p></body></html>"},
    )

    report = service.incremental()

    assert report.items_deleted == 1
    assert "onenote:page-2" in metadata_store.deleted_items
    assert "onenote:page-2" in vector_store.deleted_source_item_ids
    assert metadata_store.documents["onenote:page-1"].section_path == "Team Notebook / Moved Section"
