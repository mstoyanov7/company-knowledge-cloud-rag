from __future__ import annotations

from datetime import UTC, datetime

from shared_schemas import AppSettings, SharePointCheckpoint, SourceDocument, SyncMode

from graph_connectors.sharepoint.connector import SharePointConnector
from graph_connectors.sharepoint.models import SharePointDeltaPage, SharePointDrive, SharePointDriveItem, SharePointSite
from sync_worker.ingestion import CompositeFileExtractor, DeterministicEmbedder, TextChunker, compute_content_hash
from sync_worker.sharepoint.normalization import SharePointDocumentNormalizer
from sync_worker.sharepoint.service import SharePointSyncService


class FakeSharePointGraphClient:
    def __init__(self, pages: dict[str, SharePointDeltaPage], content_by_item_id: dict[str, bytes]) -> None:
        self.pages = pages
        self.content_by_item_id = content_by_item_id
        self.site = SharePointSite(
            id="site-1",
            name="Onboarding",
            web_url="https://contoso.sharepoint.com/sites/onboarding",
            hostname="contoso.sharepoint.com",
            relative_path="sites/onboarding",
        )
        self.drive = SharePointDrive(
            id="drive-1",
            name="Documents",
            web_url="https://contoso.sharepoint.com/sites/onboarding/Documents",
        )

    def resolve_site(self) -> SharePointSite:
        return self.site

    def list_drives(self, site_id: str) -> list[SharePointDrive]:
        return [self.drive]

    def get_drive_delta_page(self, drive_id: str, *, cursor_url=None, delta_link=None) -> SharePointDeltaPage:
        key = cursor_url or delta_link or "bootstrap"
        return self.pages[key]

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        return self.content_by_item_id[item_id]


class InMemoryMetadataStore:
    def __init__(self) -> None:
        self.checkpoints: dict[str, SharePointCheckpoint] = {}
        self.documents: dict[str, SourceDocument] = {}
        self.deleted_items: list[str] = []
        self.chunks: dict[str, list] = {}

    def ensure_schema(self) -> None:
        return None

    def get_checkpoint(self, scope_key: str) -> SharePointCheckpoint | None:
        return self.checkpoints.get(scope_key)

    def upsert_checkpoint(self, checkpoint: SharePointCheckpoint) -> SharePointCheckpoint:
        self.checkpoints[checkpoint.scope_key] = checkpoint
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


def build_service(fake_client: FakeSharePointGraphClient) -> tuple[SharePointSyncService, InMemoryMetadataStore, InMemoryVectorStore]:
    settings = AppSettings(
        app_env="test",
        sharepoint_graph_mode="mock",
        graph_sharepoint_hostname="contoso.sharepoint.com",
        graph_sharepoint_site_scope="sites/onboarding",
        graph_sharepoint_drive_scope="Documents",
        sharepoint_chunk_size_chars=60,
        sharepoint_chunk_overlap_chars=10,
    )
    connector = SharePointConnector(settings, client=fake_client)
    metadata_store = InMemoryMetadataStore()
    vector_store = InMemoryVectorStore()
    service = SharePointSyncService(
        settings=settings,
        connector=connector,
        extractor=CompositeFileExtractor(),
        normalizer=SharePointDocumentNormalizer(),
        chunker=TextChunker(settings),
        embedder=DeterministicEmbedder(settings),
        metadata_store=metadata_store,
        vector_store=vector_store,
    )
    return service, metadata_store, vector_store


def make_file_item(item_id: str, *, deleted: bool = False) -> SharePointDriveItem:
    return SharePointDriveItem(
        id=item_id,
        name="day1-checklist.txt",
        web_url="https://contoso.sharepoint.com/sites/onboarding/Documents/day1-checklist.txt",
        parent_path="/drive/root:/General",
        file_name="day1-checklist.txt",
        file_extension="txt",
        mime_type="text/plain",
        size=128,
        is_file=not deleted,
        is_deleted=deleted,
        last_modified_utc=datetime(2026, 4, 24, tzinfo=UTC),
    )


def test_compute_content_hash_normalizes_line_endings() -> None:
    assert compute_content_hash("line1\r\nline2\r\n") == compute_content_hash("line1\nline2")


def test_sharepoint_normalizer_preserves_metadata() -> None:
    normalizer = SharePointDocumentNormalizer()
    site = SharePointSite(
        id="site-1",
        name="Onboarding",
        web_url="https://contoso.sharepoint.com/sites/onboarding",
        hostname="contoso.sharepoint.com",
        relative_path="sites/onboarding",
    )
    drive = SharePointDrive(
        id="drive-1",
        name="Documents",
        web_url="https://contoso.sharepoint.com/sites/onboarding/Documents",
    )
    item = make_file_item("item-1")
    document = normalizer.normalize(
        site=site,
        drive=drive,
        item=item,
        extracted_content=CompositeFileExtractor().extract("day1-checklist.txt", b"First day setup instructions"),
    )

    assert document.source_item_id == "item-1"
    assert document.source_container == "sites/onboarding/Documents"
    assert document.metadata["drive_id"] == "drive-1"
    assert document.metadata["extractor"] == "plain-text"


def test_sharepoint_bootstrap_persists_checkpoint_and_chunks() -> None:
    fake_client = FakeSharePointGraphClient(
        pages={
            "bootstrap": SharePointDeltaPage(items=[make_file_item("item-1")], delta_link="delta-1"),
        },
        content_by_item_id={"item-1": b"First day checklist for payroll, VPN, and laptop setup."},
    )
    service, metadata_store, vector_store = build_service(fake_client)

    report = service.bootstrap()

    assert report.items_changed == 1
    assert report.checkpoint is not None
    assert report.checkpoint.delta_link == "delta-1"
    assert "item-1" in metadata_store.documents
    assert "item-1" in metadata_store.chunks
    assert "item-1" in vector_store.upserts


def test_sharepoint_incremental_skips_unchanged_and_updates_checkpoint() -> None:
    fake_client = FakeSharePointGraphClient(
        pages={
            "bootstrap": SharePointDeltaPage(items=[make_file_item("item-1")], delta_link="delta-1"),
            "delta-1": SharePointDeltaPage(items=[make_file_item("item-1")], delta_link="delta-2"),
        },
        content_by_item_id={"item-1": b"Same content for repeated delta sync."},
    )
    service, metadata_store, _ = build_service(fake_client)

    bootstrap_report = service.bootstrap()
    incremental_report = service.incremental()

    assert bootstrap_report.checkpoint is not None
    assert incremental_report.items_skipped == 1
    assert metadata_store.get_checkpoint(service.settings.sharepoint_scope_key).delta_link == "delta-2"


def test_sharepoint_incremental_handles_deleted_items() -> None:
    fake_client = FakeSharePointGraphClient(
        pages={
            "bootstrap": SharePointDeltaPage(items=[make_file_item("item-1")], delta_link="delta-1"),
            "delta-1": SharePointDeltaPage(items=[make_file_item("item-1", deleted=True)], delta_link="delta-2"),
        },
        content_by_item_id={"item-1": b"Some content before deletion."},
    )
    service, metadata_store, vector_store = build_service(fake_client)

    service.bootstrap()
    report = service.incremental()

    assert report.items_deleted == 1
    assert "item-1" in metadata_store.deleted_items
    assert "item-1" in vector_store.deleted_source_item_ids
    assert metadata_store.get_checkpoint(service.settings.sharepoint_scope_key).delta_link == "delta-2"
