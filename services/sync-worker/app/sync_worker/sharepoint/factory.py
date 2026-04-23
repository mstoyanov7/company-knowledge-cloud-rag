from __future__ import annotations

from shared_schemas import AppSettings

from graph_connectors.sharepoint.connector import SharePointConnector
from sync_worker.ingestion import CompositeFileExtractor, DeterministicEmbedder, TextChunker
from sync_worker.persistence import PostgresMetadataStore, QdrantChunkStore
from sync_worker.sharepoint.normalization import SharePointDocumentNormalizer
from sync_worker.sharepoint.service import SharePointSyncService


def build_sharepoint_sync_service(settings: AppSettings) -> SharePointSyncService:
    return SharePointSyncService(
        settings=settings,
        connector=SharePointConnector(settings),
        extractor=CompositeFileExtractor(),
        normalizer=SharePointDocumentNormalizer(),
        chunker=TextChunker(
            settings,
            chunk_size_chars=settings.sharepoint_chunk_size_chars,
            chunk_overlap_chars=settings.sharepoint_chunk_overlap_chars,
        ),
        embedder=DeterministicEmbedder(settings),
        metadata_store=PostgresMetadataStore(settings),
        vector_store=QdrantChunkStore(settings, collection_name=settings.sharepoint_vector_collection),
    )
