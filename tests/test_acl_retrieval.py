from __future__ import annotations

from shared_schemas import AccessScope

from datetime import UTC, datetime

from shared_schemas import ChunkDocument

from rag_api.adapters.retrieval.qdrant import QdrantAclRetriever, lexical_relevance_score


def test_qdrant_acl_filter_includes_tenant_acl_and_source_scope() -> None:
    access_scope = AccessScope(
        user_id="u1",
        email="u1@example.com",
        tenant_id="tenant-1",
        allowed_acl_tags=["public", "engineering"],
        source_filters=["onenote"],
    )

    payload_filter = QdrantAclRetriever.build_payload_filter(access_scope).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )

    assert payload_filter["must"][0] == {"key": "tenant_id", "match": {"value": "tenant-1"}}
    assert payload_filter["must"][1] == {"key": "acl_tags", "match": {"any": ["public", "engineering"]}}
    assert payload_filter["must"][2] == {"key": "source_system", "match": {"any": ["onenote"]}}


def _chunk(title: str, text: str) -> ChunkDocument:
    return ChunkDocument(
        tenant_id="local-tenant",
        source_system="onenote",
        source_container="onenote",
        source_item_id=title,
        source_url="https://example.test",
        title=title,
        section_path="Notebook / Section",
        last_modified_utc=datetime(2026, 5, 17, tzinfo=UTC),
        acl_tags=["employees"],
        content_hash="hash",
        chunk_id=f"{title}-chunk",
        chunk_index=0,
        chunk_text=text,
        embedding_model="token-hash-v1",
    )


def test_lexical_relevance_prefers_question_matching_chunk() -> None:
    question = "How do I configure Docker?"
    docker_chunk = _chunk("Developer setup", "Install Docker Desktop and configure Git credentials.")
    benefits_chunk = _chunk("Benefits", "Review medical insurance and wellness benefits.")

    assert lexical_relevance_score(question, docker_chunk) > lexical_relevance_score(question, benefits_chunk)
    assert lexical_relevance_score(question, benefits_chunk) == 0


def test_lexical_relevance_prefers_exact_working_hours_definition() -> None:
    question = "Whate are the working hours?"
    definition_chunk = _chunk(
        "Working Hours",
        "Standard working hours: 09:00 - 18:00 (Monday-Friday)\n"
        "Flexible start: 08:00 - 10:00 (must complete 8 hours)",
    )
    mention_chunk = _chunk(
        "Slack availability",
        "Employees must be available on Slack during working hours.",
    )

    assert lexical_relevance_score(question, definition_chunk) > lexical_relevance_score(question, mention_chunk)
    assert lexical_relevance_score(question, mention_chunk) == 0


def test_lexical_relevance_uses_planned_query_terms() -> None:
    question = "remote work policy work from home allowed approval"
    remote_chunk = _chunk(
        "HR Policies",
        "# Remote Work Policy\n"
        "Allowed: up to 3 days per week\n"
        "Must be approved by manager\n"
        "Employees must be available on Slack during working hours",
    )
    unrelated_chunk = _chunk(
        "Developer setup",
        "Install Docker Desktop and configure Git credentials.",
    )

    assert lexical_relevance_score(question, remote_chunk) > 0
    assert lexical_relevance_score(question, remote_chunk) > lexical_relevance_score(question, unrelated_chunk)


class _FakeScrollClient:
    """Minimal Qdrant client double that paginates points via offset, so the
    target page only appears after the first batch."""

    def __init__(self, payloads: list[dict], *, batch: int = 2) -> None:
        self._payloads = payloads
        self._batch = batch
        self.scroll_calls = 0

    def get_collections(self):  # pragma: no cover - unused here
        return None

    def query_points(self, **_kwargs):
        class _Empty:
            points: list = []

        return _Empty()

    def scroll(self, *, collection_name, scroll_filter, limit, offset=None, with_payload, with_vectors):
        self.scroll_calls += 1
        start = int(offset or 0)
        window = self._payloads[start : start + self._batch]
        points = [type("P", (), {"payload": payload}) for payload in window]
        next_offset = start + self._batch
        has_more = next_offset < len(self._payloads)
        return points, (next_offset if has_more else None)


def _payload(title: str, text: str, item_id: str) -> dict:
    return {
        "tenant_id": "local-tenant",
        "source_system": "onenote",
        "source_container": "onenote",
        "source_item_id": item_id,
        "source_url": "https://example.test",
        "title": title,
        "section_path": "Notebook / Section",
        "last_modified_utc": "2026-05-17T00:00:00+00:00",
        "acl_tags": ["employees"],
        "content_hash": item_id,
        "chunk_id": f"{item_id}-0",
        "chunk_index": 0,
        "chunk_text": text,
        "embedding_model": "token-hash-v1",
        "tags": [],
        "metadata": {},
    }


def _retriever_with_client(client) -> QdrantAclRetriever:
    from shared_schemas import AppSettings

    retriever = QdrantAclRetriever.__new__(QdrantAclRetriever)
    retriever.settings = AppSettings()  # retrieval_lexical_scan_limit defaults to 0 (scan all)
    retriever.client = client
    return retriever


def test_lexical_scan_paginates_to_find_title_match_past_first_batch() -> None:
    # The Flutter page is the very last point; a single-batch scan would miss it.
    payloads = [
        _payload(f"Filler Page {index}", "unrelated onboarding notes", f"filler-{index}") for index in range(6)
    ]
    payloads.append(_payload("Flutter Embedded HMI Setup", "Steps to set up the Flutter project.", "flutter"))
    client = _FakeScrollClient(payloads, batch=2)
    retriever = _retriever_with_client(client)

    candidates = retriever._lexical_candidates("onenote_chunks", object(), "how to setup flutter project")

    titles = {chunk.title for chunk in candidates}
    assert "Flutter Embedded HMI Setup" in titles
    assert client.scroll_calls > 1  # proves pagination happened
