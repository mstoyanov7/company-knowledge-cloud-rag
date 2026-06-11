from __future__ import annotations

import logging
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models
from shared_schemas import AppSettings, ChunkDocument

logger = logging.getLogger(__name__)


def _is_vector_dimension_error(error: Exception) -> bool:
    """True when Qdrant rejected an op because the vector dimension does not match
    the collection (e.g. 768-dim vectors into a 32-dim collection)."""
    text = str(error).lower()
    return "vector dimension error" in text or ("expected dim" in text and "got" in text)


class QdrantChunkStore:
    def __init__(self, settings: AppSettings, *, collection_name: str | None = None) -> None:
        self.settings = settings
        self.collection_name = collection_name or settings.onenote_vector_collection
        self.client = QdrantClient(url=settings.qdrant_url)

    def ensure_collection(self) -> None:
        desired_size = self.settings.embedding_vector_size
        collections = self.client.get_collections().collections
        exists = any(collection.name == self.collection_name for collection in collections)
        if exists:
            current_size = self._current_vector_size()
            if current_size is not None and current_size != desired_size:
                # The embedding model changed dimension (e.g. the 32-dim token-hash
                # fallback -> 768-dim nomic-embed-text). Cosine search across two
                # dimensions is invalid, so rebuild the collection. This drops the
                # old vectors; a full re-index must follow.
                logger.warning(
                    "Recreating Qdrant collection '%s': vector size %s -> %s. Re-index required.",
                    self.collection_name,
                    current_size,
                    desired_size,
                )
                self._recreate_collection()
                return
        if not exists:
            self._create_collection()
            return
        self._ensure_payload_indexes()

    def _create_collection(self) -> None:
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.settings.embedding_vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        self._ensure_payload_indexes()

    def _recreate_collection(self) -> None:
        try:
            self.client.delete_collection(collection_name=self.collection_name)
        except Exception:
            logger.exception("Failed to delete Qdrant collection '%s' before recreate.", self.collection_name)
        self._create_collection()

    def _current_vector_size(self) -> int | None:
        try:
            params = self.client.get_collection(self.collection_name).config.params.vectors
        except Exception:
            return None
        # Single unnamed vector -> VectorParams with .size. Named vectors -> dict of
        # {name: VectorParams}; this store only ever creates a single unnamed vector,
        # so take the first entry's size if a dict is ever encountered.
        size = getattr(params, "size", None)
        if size is None and isinstance(params, dict) and params:
            first = next(iter(params.values()))
            size = getattr(first, "size", None)
        return int(size) if size is not None else None

    def upsert_chunks(self, chunks: list[ChunkDocument], embeddings: list[list[float]]) -> None:
        points = []
        for chunk, vector in zip(chunks, embeddings, strict=True):
            points.append(
                models.PointStruct(
                    id=self.point_id_for_chunk_id(chunk.chunk_id),
                    vector=vector,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "tenant_id": chunk.tenant_id,
                        "source_item_id": chunk.source_item_id,
                        "source_system": chunk.source_system,
                        "source_container": chunk.source_container,
                        "source_url": chunk.source_url,
                        "title": chunk.title,
                        "section_path": chunk.section_path,
                        "last_modified_utc": chunk.last_modified_utc.isoformat(),
                        "acl_tags": chunk.acl_tags,
                        "acl_bindings": [binding.model_dump(mode="json") for binding in chunk.acl_bindings],
                        "content_hash": chunk.content_hash,
                        "chunk_index": chunk.chunk_index,
                        "chunk_text": chunk.chunk_text,
                        "embedding_model": chunk.embedding_model,
                        "language": chunk.language,
                        "tags": chunk.tags,
                        "metadata": chunk.metadata,
                    },
                )
            )
        if not points:
            return
        try:
            self.client.upsert(collection_name=self.collection_name, wait=True, points=points)
        except Exception as error:
            if not _is_vector_dimension_error(error):
                raise
            # The collection predates the current embedding model (wrong dimension).
            # Rebuild it and retry once so a stale 32-dim collection self-heals into
            # the new 768-dim one instead of failing every sync.
            logger.warning(
                "Vector dimension mismatch upserting to '%s'; recreating collection and retrying.",
                self.collection_name,
            )
            self._recreate_collection()
            self.client.upsert(collection_name=self.collection_name, wait=True, points=points)

    def delete_chunks_for_source_item(self, source_item_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            wait=True,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_item_id",
                            match=models.MatchValue(value=source_item_id),
                        )
                    ]
                )
            ),
        )

    @staticmethod
    def point_id_for_chunk_id(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, chunk_id))

    def _ensure_payload_indexes(self) -> None:
        for field_name in [
            "tenant_id",
            "acl_tags",
            "source_system",
            "source_container",
            "source_item_id",
            "metadata.section_name",
        ]:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            except Exception:
                continue
