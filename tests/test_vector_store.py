from __future__ import annotations

from uuid import UUID

from sync_worker.persistence.vector_store import QdrantChunkStore


def test_qdrant_point_id_is_deterministic_uuid() -> None:
    chunk_id = "onenote:mock-page-001-chunk-0"

    point_id = QdrantChunkStore.point_id_for_chunk_id(chunk_id)

    assert point_id == QdrantChunkStore.point_id_for_chunk_id(chunk_id)
    assert str(UUID(point_id)) == point_id
