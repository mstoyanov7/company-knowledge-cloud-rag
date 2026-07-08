from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pypdf import PdfWriter

from shared_schemas import AppSettings, OneNoteCheckpoint, SourceAttachment, SourceDocument, SyncMode

from graph_connectors.onenote.connector import OneNoteConnector
from graph_connectors.onenote.auth import MockOneNoteDelegatedAuthProvider
from graph_connectors.onenote.client import MicrosoftGraphOneNoteClient, MockOneNoteGraphClient
from graph_connectors.onenote.models import OneNoteNotebook, OneNotePage, OneNoteSection, OneNoteSite
from sync_worker.ingestion import ChunkEmbedder, CompositeFileExtractor, TextChunker, UnsupportedFileTypeError
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer
from sync_worker.onenote.parser import NullOneNoteResourceHook, OneNoteHtmlParser
from sync_worker.onenote.service import OneNoteSyncService
from sync_worker.onenote.topic_classifier import OneNoteTopicClassifier


class FakeOneNoteGraphClient:
    def __init__(
        self,
        *,
        inventory_pages: list[OneNotePage],
        incremental_pages: list[OneNotePage] | None = None,
        content_by_url: dict[str, str],
        resource_by_url: dict[str, bytes] | None = None,
    ) -> None:
        self.inventory_pages = inventory_pages
        self.incremental_pages = incremental_pages if incremental_pages is not None else inventory_pages
        self.content_by_url = content_by_url
        self.resource_by_url = resource_by_url or {}
        self.page_calls: list[dict[str, object]] = []
        self.site = OneNoteSite(
            id="site-1",
            name="Onboarding",
            web_url="https://contoso.example.test/sites/onboarding",
            hostname="contoso.example.test",
            relative_path="sites/onboarding",
        )
        self.notebooks = [
            OneNoteNotebook(
                id="notebook-1",
                display_name="Team Notebook",
                web_url="https://contoso.example.test/sites/onboarding/TeamNotebook",
            )
        ]
        section_specs: dict[str, OneNotePage] = {}
        for page in [*self.inventory_pages, *self.incremental_pages]:
            section_specs.setdefault(page.section_id, page)
        self.sections = (
            [
                OneNoteSection(
                    id=page.section_id,
                    display_name=page.section_name,
                    notebook_id=page.notebook_id,
                    notebook_name=page.notebook_name,
                    web_url=f"https://contoso.example.test/sites/onboarding/{page.section_name.replace(' ', '%20')}",
                )
                for page in section_specs.values()
            ]
            or [
                OneNoteSection(
                    id="section-1",
                    display_name="Orientation",
                    notebook_id="notebook-1",
                    notebook_name="Team Notebook",
                    web_url="https://contoso.example.test/sites/onboarding/Orientation",
                )
            ]
        )

    def resolve_site(self) -> OneNoteSite:
        return self.site

    def list_notebooks(self, site_id: str) -> list[OneNoteNotebook]:
        return list(self.notebooks)

    def list_sections(self, site_id: str) -> list[OneNoteSection]:
        return list(self.sections)

    def list_pages(
        self,
        site_id: str,
        *,
        section_id=None,
        modified_since=None,
        next_url=None,
    ) -> tuple[list[OneNotePage], str | None]:
        self.page_calls.append(
            {
                "site_id": site_id,
                "section_id": section_id,
                "modified_since": modified_since,
                "next_url": next_url,
            }
        )
        if next_url is not None:
            return [], None
        pages = self.incremental_pages if modified_since is not None else self.inventory_pages
        if section_id is not None:
            pages = [page for page in pages if page.section_id == section_id]
        return list(pages), None

    def get_page_content(self, content_url: str) -> str:
        return self.content_by_url[content_url]

    def get_resource_content(self, resource_url: str) -> bytes:
        return self.resource_by_url[resource_url]


class InMemoryMetadataStore:
    def __init__(self) -> None:
        self.onenote_checkpoints: dict[str, OneNoteCheckpoint] = {}
        self.documents: dict[str, SourceDocument] = {}
        self.deleted_items: list[str] = []
        self.chunks: dict[str, list] = {}
        self.attachments: dict[str, SourceAttachment] = {}

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

    def upsert_source_attachment(self, scope_key: str, attachment: SourceAttachment) -> None:
        self.attachments[attachment.download_id] = attachment

    def get_source_attachment(self, download_id: str) -> SourceAttachment | None:
        return self.attachments.get(download_id)

    def list_active_source_attachments(
        self,
        scope_key: str,
        parent_source_item_ids: list[str] | None = None,
    ) -> list[SourceAttachment]:
        attachments = list(self.attachments.values())
        if parent_source_item_ids:
            parents = set(parent_source_item_ids)
            attachments = [attachment for attachment in attachments if attachment.parent_source_item_id in parents]
        return attachments

    def mark_stale_attachments_deleted(
        self,
        scope_key: str,
        parent_source_item_id: str,
        active_download_ids: set[str],
    ) -> list[SourceAttachment]:
        stale = [
            attachment
            for attachment in self.attachments.values()
            if attachment.parent_source_item_id == parent_source_item_id and attachment.download_id not in active_download_ids
        ]
        for attachment in stale:
            self.attachments.pop(attachment.download_id, None)
        return stale

    def mark_source_deleted(self, scope_key: str, source_item_id: str, deleted_at_utc=None) -> None:
        self.deleted_items.append(source_item_id)
        self.documents.pop(source_item_id, None)
        self.chunks.pop(source_item_id, None)
        for download_id, attachment in list(self.attachments.items()):
            if attachment.parent_source_item_id == source_item_id or attachment.indexed_source_item_id == source_item_id:
                self.attachments.pop(download_id, None)

    def replace_chunks(self, scope_key: str, source_item_id: str, chunks: list) -> None:
        self.chunks[source_item_id] = chunks

    def list_active_source_documents(self, scope_key: str, source_system: str) -> list[SourceDocument]:
        return [document for document in self.documents.values() if document.source_system == source_system]


class SchemaRequiredMetadataStore(InMemoryMetadataStore):
    def __init__(self) -> None:
        super().__init__()
        self.schema_ready = False

    def ensure_schema(self) -> None:
        self.schema_ready = True

    def get_onenote_checkpoint(self, scope_key: str) -> OneNoteCheckpoint | None:
        if not self.schema_ready:
            raise RuntimeError("schema was not initialized before checkpoint read")
        return super().get_onenote_checkpoint(scope_key)


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
        web_url=f"https://contoso.example.test/sites/onboarding/{page_id}",
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
        graph_onenote_site_hostname="contoso.example.test",
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
        embedder=ChunkEmbedder(settings),
        metadata_store=metadata_store,
        vector_store=vector_store,
        resource_hook=NullOneNoteResourceHook(),
    )
    return service, metadata_store, vector_store


def build_service_with_settings(
    fake_client: FakeOneNoteGraphClient,
    **settings_overrides,
) -> tuple[OneNoteSyncService, InMemoryMetadataStore, InMemoryVectorStore]:
    service, metadata_store, vector_store = build_service(fake_client)
    service.settings = service.settings.model_copy(update=settings_overrides)
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


def test_onenote_parser_removes_placeholder_artifacts_but_keeps_labeled_resources() -> None:
    parser = OneNoteHtmlParser()
    parsed = parser.parse(
        """
        <html><body>
        <p>OBJ Project setup uses Docker Desktop. \ufffc</p>
        <p>Run docker compose up after cloning.</p>
        <img src="https://graph.microsoft.com/v1.0/resources/image-1/$value" alt="OBJ" />
        <object data="https://graph.microsoft.com/v1.0/resources/file-1/$value" type="application/octet-stream"></object>
        <object data="https://graph.microsoft.com/v1.0/resources/file-2/$value" data-attachment="setup.ps1" type="text/plain"></object>
        </body></html>
        """
    )

    assert "OBJ" not in parsed.text
    assert "\ufffc" not in parsed.text
    assert "Project setup uses Docker Desktop." in parsed.text
    assert "Run docker compose up after cloning." in parsed.text
    assert "[Image:" not in parsed.text
    assert "[Attachment: setup.ps1]" in parsed.text
    assert len(parsed.resources) == 3


def test_onenote_parser_collects_file_like_links_as_attachments() -> None:
    parser = OneNoteHtmlParser()
    parsed = parser.parse(
        """
        <html><body>
        <p>Download the <a href="https://downloads.example.test/tools/setup.zip">Windows tools bundle</a>.</p>
        <p>Read <a href="https://docs.example.test/setup">the setup page</a>.</p>
        </body></html>
        """
    )

    assert len(parsed.resources) == 1
    assert parsed.resources[0].resource_origin == "link"
    assert parsed.resources[0].name == "Windows tools bundle"
    assert parsed.resources[0].resource_url.endswith("setup.zip")


def test_file_extractor_supports_readable_formats_and_rejects_legacy_or_binary_formats() -> None:
    extractor = CompositeFileExtractor()

    assert "Markdown guide" in extractor.extract("guide.md", b"# Markdown guide").text
    assert "Plain guide" in extractor.extract("guide.txt", b"Plain guide").text
    assert "Docx guide" in extractor.extract("guide.docx", _docx_bytes("Docx guide")).text
    assert "Slide guide" in extractor.extract("guide.pptx", _pptx_bytes("Slide guide")).text
    assert extractor.extract("blank.pdf", _blank_pdf_bytes()).extractor_name == "pypdf"
    for file_name in ["legacy.doc", "legacy.ppt", "archive.zip", "installer.exe"]:
        with pytest.raises(UnsupportedFileTypeError):
            extractor.extract(file_name, b"not readable")


def test_onenote_parser_preserves_br_separated_command_lines() -> None:
    parser = OneNoteHtmlParser()
    parsed = parser.parse(
        """
        <html><body>
        <h1>Install</h1>
        <p>
        sudo apt update<br />
        sudo apt install -y build-essential cmake git libboost-all-dev tcpdump<br />
        git clone https://github.com/COVESA/vsomeip.git third_party/vsomeip<br />
        cmake -S third_party/vsomeip -B third_party/vsomeip/build<br />
        cmake --build third_party/vsomeip/build -j
        </p>
        </body></html>
        """
    )

    assert "```bash" in parsed.text
    assert "sudo apt update\nsudo apt install -y build-essential cmake git libboost-all-dev tcpdump" in parsed.text
    assert "git clone https://github.com/COVESA/vsomeip.git third_party/vsomeip\ncmake -S" in parsed.text
    assert "sudo apt update sudo apt install" not in parsed.text


def test_onenote_normalizer_attaches_topic_metadata_from_config(tmp_path) -> None:
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(
        """
        [
          {
            "id": "hr",
            "name": "HR Questions",
            "description": "Employee benefits and leave policy.",
            "retrieval_tags": ["paid leave", "benefits", "enrollment"]
          }
        ]
        """,
        encoding="utf-8",
    )
    settings = AppSettings(app_env="test", topics_config_path=str(topics_path))
    page = make_page("page-benefits", section_name="Benefits", title="Paid leave benefits checklist")
    site = OneNoteSite(
        id="site-1",
        name="Onboarding",
        web_url="https://contoso.example.test/sites/onboarding",
        hostname="contoso.example.test",
        relative_path="sites/onboarding",
    )
    parsed = OneNoteHtmlParser().parse(
        "<html><body><p>Employees should review paid leave policy and benefits enrollment.</p></body></html>"
    )
    normalizer = OneNoteDocumentNormalizer(topic_classifier=OneNoteTopicClassifier.from_settings(settings))

    document = normalizer.normalize(site=site, page=page, parsed_page=parsed)

    assert "hr" in document.metadata["topic_ids"]
    assert document.metadata["topic_source"] == "deterministic-config-match"
    assert "topic:hr" in document.tags


def test_onenote_normalizer_scopes_acl_tag_to_notebook() -> None:
    site = OneNoteSite(
        id="site-1",
        name="Onboarding",
        web_url="https://contoso.example.test/sites/onboarding",
        hostname="contoso.example.test",
        relative_path="sites/onboarding",
    )
    parsed = OneNoteHtmlParser().parse("<html><body><p>Team A only.</p></body></html>")
    normalizer = OneNoteDocumentNormalizer()

    # make_page defaults notebook_name="Team Notebook".
    team_a = normalizer.normalize(
        site=site,
        page=make_page("page-a", title="Team A welcome"),
        parsed_page=parsed,
    )

    # Each page inherits a single ACL tag derived from its notebook name, so a
    # user without that tag cannot retrieve the page.
    assert team_a.acl_tags == ["team-notebook"]
    assert team_a.metadata["acl_source"] == "notebook-scoped"


def test_mock_onenote_client_uses_all_notebooks_when_scope_is_blank() -> None:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="mock",
        graph_onenote_site_hostname="contoso.example.test",
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


def test_live_onenote_client_paginates_sections() -> None:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="live",
        graph_onenote_scope_mode="me",
        onenote_retry_attempts=1,
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if len(requested_urls) == 1:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "section-1",
                            "displayName": "Orientation",
                            "parentNotebook": {"id": "notebook-1", "displayName": "Team Notebook"},
                        }
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onenote/sections?$skip=100",
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "section-2",
                        "displayName": "Tooling",
                        "parentNotebook": {"id": "notebook-1", "displayName": "Team Notebook"},
                    }
                ]
            },
        )

    client = MicrosoftGraphOneNoteClient(
        settings,
        auth_provider=MockOneNoteDelegatedAuthProvider(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sections = client.list_sections("me")

    assert [section.id for section in sections] == ["section-1", "section-2"]
    assert requested_urls[0].startswith("https://graph.microsoft.com/v1.0/me/onenote/sections?")
    assert requested_urls[1] == "https://graph.microsoft.com/v1.0/me/onenote/sections?$skip=100"


def test_live_onenote_client_lists_pages_by_section() -> None:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="live",
        graph_onenote_scope_mode="me",
        onenote_retry_attempts=1,
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "page-1",
                        "title": "Welcome",
                        "contentUrl": "https://graph.microsoft.com/v1.0/me/onenote/pages/page-1/content",
                        "createdDateTime": "2026-04-24T08:00:00Z",
                        "lastModifiedDateTime": "2026-04-24T09:00:00Z",
                        "parentNotebook": {"id": "notebook-1", "displayName": "Team Notebook"},
                        "parentSection": {"id": "section/one", "displayName": "Orientation"},
                    }
                ]
            },
        )

    client = MicrosoftGraphOneNoteClient(
        settings,
        auth_provider=MockOneNoteDelegatedAuthProvider(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    pages, next_url = client.list_pages(
        "me",
        section_id="section/one",
        modified_since=datetime(2026, 4, 24, 8, 30, tzinfo=UTC),
    )

    assert next_url is None
    assert pages[0].id == "page-1"
    assert "/me/onenote/sections/section%2Fone/pages?" in requested_urls[0]
    assert "%24filter=lastModifiedDateTime+ge+2026-04-24T08%3A30%3A00Z" in requested_urls[0]
    assert "pagelevel=true" in requested_urls[0]


def test_onenote_personal_scope_does_not_require_site_configuration() -> None:
    settings = AppSettings(
        app_env="test",
        onenote_graph_mode="mock",
        graph_onenote_scope_mode="me",
        graph_onenote_site_hostname="",
        graph_onenote_site_scope="",
        graph_onenote_notebook_scope="",
    )
    connector = OneNoteConnector(settings, client=MockOneNoteGraphClient(settings))

    site, notebooks, sections = connector.resolve_scope()

    assert site.id == "me"
    assert site.hostname == "me"
    assert site.relative_path == "onenote"
    assert settings.onenote_scope_key == "onenote::me::personal::all-notebooks"
    assert "/me/onenote" in connector.describe_scope()
    assert {notebook.display_name for notebook in notebooks} == {"Team Notebook", "Engineering Notebook"}
    assert {section.display_name for section in sections} == {"Orientation", "Tooling"}


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


def test_onenote_incremental_lookback_reindexes_content_when_graph_timestamp_does_not_advance() -> None:
    older_page = make_page("page-1", last_modified=datetime(2026, 4, 24, 9, 0, tzinfo=UTC))
    newer_page = make_page("page-2", last_modified=datetime(2026, 4, 24, 10, 0, tzinfo=UTC))
    service, metadata_store, vector_store = build_service_with_settings(
        FakeOneNoteGraphClient(
            inventory_pages=[older_page, newer_page],
            content_by_url={
                older_page.content_url: "<html><body><p>Original content.</p></body></html>",
                newer_page.content_url: "<html><body><p>Newer page content.</p></body></html>",
            },
        ),
        onenote_incremental_lookback_seconds=int(timedelta(hours=2).total_seconds()),
    )
    service.bootstrap()

    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=[older_page, newer_page],
        incremental_pages=[older_page, newer_page],
        content_by_url={
            older_page.content_url: "<html><body><p>Updated content that Graph did not timestamp.</p></body></html>",
            newer_page.content_url: "<html><body><p>Newer page content.</p></body></html>",
        },
    )

    report = service.incremental()

    assert report.items_changed == 1
    assert "Updated content that Graph did not timestamp." in metadata_store.documents["onenote:page-1"].content_text
    assert "onenote:page-1" in vector_store.upserts


def _document_with_acl_tags(acl_tags: list[str]) -> SourceDocument:
    return SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/onboarding/Team Notebook",
        source_item_id="onenote:page-1",
        source_url="https://contoso.example.test/sites/onboarding/page-1",
        title="Welcome checklist",
        file_name="Welcome checklist.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Team Notebook / Orientation",
        last_modified_utc=datetime(2026, 4, 24, 9, 0, tzinfo=UTC),
        acl_tags=acl_tags,
        content_hash="same-hash",
        content_text="identical body",
        tags=["onenote"],
        metadata={"section_id": "section-1", "notebook_id": "notebook-1", "page_order": 0},
    )


def test_onenote_document_changed_detects_acl_tag_mapping_change() -> None:
    service, _metadata_store, _vector_store = build_service(
        FakeOneNoteGraphClient(
            inventory_pages=[make_page("page-1")],
            content_by_url={"mock://onenote/page-1": "<html><body><p>Body.</p></body></html>"},
        )
    )
    existing = _document_with_acl_tags(["employees"])
    # Same content, only the access-tag mapping changed: must still re-index so
    # the page does not keep stale ACL tags until its text next changes.
    relabeled = _document_with_acl_tags(["employees", "hr-restricted"])

    assert service._document_changed(existing, relabeled) is True
    assert service._document_changed(existing, _document_with_acl_tags(["employees"])) is False


def test_onenote_incremental_initializes_schema_before_checkpoint_lookup() -> None:
    page = make_page("page-1")
    service, _metadata_store, vector_store = build_service(
        FakeOneNoteGraphClient(
            inventory_pages=[page],
            content_by_url={page.content_url: "<html><body><p>Initial content.</p></body></html>"},
        )
    )
    metadata_store = SchemaRequiredMetadataStore()
    service.metadata_store = metadata_store

    report = service.incremental()

    assert metadata_store.schema_ready is True
    assert report.job_name == "onenote_bootstrap"
    assert vector_store.upserts


def test_onenote_incremental_lists_pages_one_section_at_a_time() -> None:
    first_page = make_page("page-1", last_modified=datetime(2026, 4, 24, 9, 0, tzinfo=UTC))
    second_page = make_page(
        "page-2",
        section_name="Tooling",
        last_modified=datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
        title="Engineering setup",
    )
    fake_client = FakeOneNoteGraphClient(
        inventory_pages=[first_page, second_page],
        incremental_pages=[first_page, second_page],
        content_by_url={
            first_page.content_url: "<html><body><p>Welcome content.</p></body></html>",
            second_page.content_url: "<html><body><p>Tooling content.</p></body></html>",
        },
    )
    service, metadata_store, _ = build_service(fake_client)
    metadata_store.upsert_onenote_checkpoint(
        OneNoteCheckpoint(
            scope_key=service.settings.onenote_scope_key,
            sync_mode=SyncMode.bootstrap,
            site_id="site-1",
            notebook_scope="Team Notebook",
            last_modified_cursor_utc=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
            page_count=0,
            item_count=0,
            updated_at_utc=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
        )
    )

    report = service.incremental()

    assert report.items_changed == 2
    assert {call["section_id"] for call in fake_client.page_calls} == {"section-1", "section-2"}
    assert all(call["section_id"] is not None for call in fake_client.page_calls)


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
    metadata_store.documents["onenote-attachment:old-download"] = SourceDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/onboarding/Team Notebook",
        source_item_id="onenote-attachment:old-download",
        source_url="/api/v1/attachments/old-download/download",
        title="old-guide.txt",
        file_name="old-guide.txt",
        file_extension="txt",
        mime_type="text/plain",
        section_path="Team Notebook / Orientation / Attachments",
        last_modified_utc=deleted_page.last_modified_utc,
        acl_tags=[],
        content_hash="old-attachment-hash",
        content_text="old deleted attachment",
        tags=["onenote", "attachment"],
        metadata={"document_kind": "attachment", "parent_source_item_id": "onenote:page-2"},
    )
    metadata_store.attachments["old-download"] = SourceAttachment(
        download_id="old-download",
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="sites/onboarding/Team Notebook",
        parent_source_item_id="onenote:page-2",
        parent_title=deleted_page.title,
        source_url=deleted_page.web_url,
        resource_url="mock://old-guide",
        file_name="old-guide.txt",
        file_extension="txt",
        size_bytes=10,
        readable=True,
        indexed_source_item_id="onenote-attachment:old-download",
        storage_path="aa/old-download.txt",
        content_hash="old-attachment-hash",
        acl_tags=[],
    )
    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=[moved_page],
        incremental_pages=[],
        content_by_url={moved_page.content_url: "<html><body><p>Original content.</p></body></html>"},
    )

    report = service.reconciliation()

    assert report.items_deleted == 1
    assert "onenote:page-2" in metadata_store.deleted_items
    assert "onenote-attachment:old-download" in metadata_store.deleted_items
    assert "onenote:page-2" in vector_store.deleted_source_item_ids
    assert "onenote-attachment:old-download" in vector_store.deleted_source_item_ids
    assert metadata_store.documents["onenote:page-1"].section_path == "Team Notebook / Moved Section"


def test_onenote_sync_indexes_readable_attachments_and_stores_unsupported_downloads(tmp_path) -> None:
    page = make_page("page-attachments", title="Project setup")
    text_url = "mock://onenote/resources/setup-guide.txt"
    exe_url = "mock://onenote/resources/setup-installer.exe"
    service, metadata_store, vector_store = build_service_with_settings(
        FakeOneNoteGraphClient(
            inventory_pages=[page],
            content_by_url={
                page.content_url: f"""
                <html><body>
                <h1>Setup</h1>
                <p>Use the attached setup guide and installer.</p>
                <object data="{text_url}" data-attachment="setup-guide.txt" type="text/plain"></object>
                <object data="{exe_url}" data-attachment="setup-installer.exe" type="application/octet-stream"></object>
                </body></html>
                """
            },
            resource_by_url={
                text_url: b"Installer step 2: run setup-installer.exe after reading the guide.",
                exe_url: b"\x00\x01binary installer",
            },
        ),
        attachment_storage_dir=str(tmp_path / "attachments"),
    )

    report = service.bootstrap()

    attachments = list(metadata_store.attachments.values())
    assert report.items_changed == 1
    assert {attachment.file_name for attachment in attachments} == {"setup-guide.txt", "setup-installer.exe"}
    guide = next(attachment for attachment in attachments if attachment.file_name == "setup-guide.txt")
    installer = next(attachment for attachment in attachments if attachment.file_name == "setup-installer.exe")
    assert guide.readable is True
    assert guide.indexed_source_item_id in metadata_store.documents
    assert "Installer step 2" in metadata_store.documents[guide.indexed_source_item_id].content_text
    assert guide.indexed_source_item_id in vector_store.upserts
    assert installer.readable is False
    assert installer.indexed_source_item_id is None
    assert (tmp_path / "attachments" / installer.storage_path).exists()
    assert len(metadata_store.documents["onenote:page-attachments"].metadata["attachment_refs"]) == 2


def test_attachment_index_carries_parent_page_title_for_name_based_questions(tmp_path) -> None:
    # A page whose content lives entirely in a readme.md attachment - the page
    # name ("ModelViewer") must be searchable on the indexed attachment so a
    # question naming the page matches it even though the file text never says
    # "ModelViewer".
    page = make_page("page-modelviewer", title="ModelViewer")
    readme_url = "mock://onenote/resources/readme.md"
    service, metadata_store, _vector_store = build_service_with_settings(
        FakeOneNoteGraphClient(
            inventory_pages=[page],
            content_by_url={
                page.content_url: (
                    f'<html><body><h1>ModelViewer</h1>'
                    f'<object data="{readme_url}" data-attachment="readme.md" type="text/markdown"></object>'
                    f"</body></html>"
                )
            },
            resource_by_url={
                readme_url: b"# Overview\nRenders 3D meshes in the browser with WebGL.\n## Usage\nStart the dev server.",
            },
        ),
        attachment_storage_dir=str(tmp_path / "attachments"),
    )

    service.bootstrap()

    attachment = next(
        document
        for document in metadata_store.documents.values()
        if document.metadata.get("document_kind") == "attachment"
    )
    haystack = " ".join([attachment.title, attachment.section_path or "", attachment.content_text]).lower()
    assert "modelviewer" in haystack  # page name is searchable even though the file text omits it
    assert "readme.md" in attachment.title.lower()  # filename preserved for display
    assert attachment.metadata.get("parent_title") == "ModelViewer"


def _docx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def _pptx_bytes(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
            ),
        )
    return buffer.getvalue()


def _blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
