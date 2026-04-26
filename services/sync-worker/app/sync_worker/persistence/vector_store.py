from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models
from shared_schemas import AppSettings, ChunkDocument


class QdrantChunkStore:
    def __init__(self, settings: AppSettings, *, collection_name: str | None = None) -> None:
        self.settings = settings
        self.collection_name = collection_name or settings.sharepoint_vector_collection
        self.client = QdrantClient(url=settings.qdrant_url)

    def ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        if not any(collection.name == self.collection_name for collection in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=self.settings.embedding_vector_size, distance=models.Distance.COSINE),
            )
        self._ensure_payload_indexes()

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
        if points:
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
        for field_name in ["tenant_id", "acl_tags", "source_system", "source_container", "source_item_id"]:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            except Exception:
                continue
