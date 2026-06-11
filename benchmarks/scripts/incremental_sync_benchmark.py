"""Quantify the savings of incremental OneNote synchronisation.

Runs three scenarios over a synthetic corpus the size of the test manifest
(~54 pages) using the mock Graph connector and the deterministic in-memory
stores, so it is fully reproducible offline and counts *operations* rather than
real embedding/Graph latency:

    A. Full initial sync (bootstrap)        — every page embedded and upserted.
    B. Incremental run after editing 3 pages — only the 3 changed pages re-done.
    C. Incremental run with 0 changes        — nothing embedded or upserted.

Measured per scenario: wall time, pages seen, pages re-indexed, pages skipped,
embedding computations and vector upserts.

Run from the repo root:

    python benchmarks/scripts/incremental_sync_benchmark.py

The deterministic in-memory doubles live in the test suite; we reuse them so the
benchmark exercises exactly the verified sync logic instead of a re-implementation.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from shared_schemas import AppSettings  # noqa: E402

from graph_connectors.onenote.connector import OneNoteConnector  # noqa: E402
from sync_worker.ingestion import ChunkEmbedder, TextChunker  # noqa: E402
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer  # noqa: E402
from sync_worker.onenote.parser import NullOneNoteResourceHook, OneNoteHtmlParser  # noqa: E402
from sync_worker.onenote.service import OneNoteSyncService  # noqa: E402

from test_onenote_sync import (  # noqa: E402
    FakeOneNoteGraphClient,
    InMemoryMetadataStore,
    InMemoryVectorStore,
    make_page,
)

PAGE_COUNT = 54
SECTIONS = ["Orientation", "Tooling"]


def page_html(index: int, revision: int = 0) -> str:
    """Multi-paragraph body large enough to chunk into a few parts."""
    bump = f"<p>Revision marker {revision}.</p>" if revision else ""
    body = " ".join(
        f"Step {step} for procedure {index}: configure the relevant service, "
        f"verify access, and record the outcome in the runbook."
        for step in range(1, 9)
    )
    return (
        f"<html><body><h1>Page {index} procedure</h1>"
        f"<p>{body}</p>"
        f"<ul><li>Owner: team {index % 7}</li><li>ETA: day {index % 5 + 1}</li></ul>"
        f"{bump}</body></html>"
    )


def build_corpus(revisions: dict[int, int] | None = None):
    revisions = revisions or {}
    pages = []
    content = {}
    for index in range(1, PAGE_COUNT + 1):
        section = SECTIONS[index % len(SECTIONS)]
        page = make_page(
            f"bench-page-{index:03d}",
            section_name=section,
            last_modified=datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
            title=f"Procedure {index}",
        )
        pages.append(page)
        content[page.content_url] = page_html(index, revisions.get(index, 0))
    return pages, content


class CountingEmbedder(ChunkEmbedder):
    embedding_calls = 0

    def embed_chunks(self, chunks):
        result = super().embed_chunks(chunks)
        CountingEmbedder.embedding_calls += len(result)
        return result


class CountingVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.upsert_vectors = 0
        self.delete_calls = 0

    def upsert_chunks(self, chunks, embeddings) -> None:
        self.upsert_vectors += len(embeddings)
        super().upsert_chunks(chunks, embeddings)

    def delete_chunks_for_source_item(self, source_item_id: str) -> None:
        self.delete_calls += 1
        super().delete_chunks_for_source_item(source_item_id)


def build_service(client: FakeOneNoteGraphClient):
    settings = AppSettings(
        app_env="bench",
        onenote_graph_mode="mock",
        graph_onenote_site_hostname="contoso.example.test",
        graph_onenote_site_scope="sites/onboarding",
        graph_onenote_notebook_scope="Team Notebook",
        # Offline lexical embedder: the benchmark counts operations, not real
        # embedding latency, so it must not reach out to Ollama.
        default_embedding_provider="token-hash-v1",
    )
    metadata_store = InMemoryMetadataStore()
    vector_store = CountingVectorStore()
    service = OneNoteSyncService(
        settings=settings,
        connector=OneNoteConnector(settings, client=client),
        parser=OneNoteHtmlParser(),
        normalizer=OneNoteDocumentNormalizer(),
        chunker=TextChunker(settings),
        embedder=CountingEmbedder(settings),
        metadata_store=metadata_store,
        vector_store=vector_store,
        resource_hook=NullOneNoteResourceHook(),
    )
    return service, vector_store


def measure(label: str, fn):
    CountingEmbedder.embedding_calls = 0
    started = time.perf_counter()
    report = fn()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "label": label,
        "elapsed_ms": elapsed_ms,
        "pages_seen": report.items_seen,
        "reindexed": report.items_changed,
        "skipped": report.items_skipped,
        "embeddings": CountingEmbedder.embedding_calls,
        "chunks_written": report.chunks_written,
    }


def main() -> None:
    pages, content = build_corpus()
    client = FakeOneNoteGraphClient(inventory_pages=pages, content_by_url=content)
    service, vector_store = build_service(client)

    # Scenario A: full initial sync.
    vector_store.upsert_vectors = 0
    row_a = measure("A. Full initial sync (bootstrap)", service.bootstrap)
    row_a["vector_upserts"] = vector_store.upsert_vectors

    # Scenario B: incremental after editing 3 pages.
    changed_indexes = {5, 17, 42}
    _, changed_content = build_corpus({i: 1 for i in changed_indexes})
    changed_pages = [p for p in pages if int(p.id.split("-")[-1]) in changed_indexes]
    merged = dict(content)
    for p in changed_pages:
        merged[p.content_url] = changed_content[p.content_url]
    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=pages,
        incremental_pages=changed_pages,
        content_by_url=merged,
    )
    vector_store.upsert_vectors = 0
    row_b = measure("B. Incremental, 3 pages edited", service.incremental)
    row_b["vector_upserts"] = vector_store.upsert_vectors

    # Scenario C: incremental with no changes.
    service.connector.client = FakeOneNoteGraphClient(
        inventory_pages=pages,
        incremental_pages=[],
        content_by_url=content,
    )
    vector_store.upsert_vectors = 0
    row_c = measure("C. Incremental, 0 changes", service.incremental)
    row_c["vector_upserts"] = vector_store.upsert_vectors

    header = f"{'Scenario':<34}{'pages':>7}{'reindex':>9}{'skip':>6}{'embed':>7}{'upserts':>9}{'ms':>9}"
    print(header)
    print("-" * len(header))
    for row in (row_a, row_b, row_c):
        print(
            f"{row['label']:<34}{row['pages_seen']:>7}{row['reindexed']:>9}"
            f"{row['skipped']:>6}{row['embeddings']:>7}{row['vector_upserts']:>9}"
            f"{row['elapsed_ms']:>9.0f}"
        )


if __name__ == "__main__":
    main()
