from __future__ import annotations

from shared_schemas import AppSettings

from graph_connectors.onenote.connector import OneNoteConnector
from sync_worker.ingestion import DeterministicEmbedder, TextChunker
from sync_worker.onenote.normalization import OneNoteDocumentNormalizer
from sync_worker.onenote.parser import NullOneNoteResourceHook, OneNoteHtmlParser
from sync_worker.onenote.service import OneNoteSyncService
from sync_worker.persistence import PostgresMetadataStore, QdrantChunkStore


def build_onenote_sync_service(settings: AppSettings) -> OneNoteSyncService:
    return OneNoteSyncService(
        settings=settings,
        connector=OneNoteConnector(settings),
        parser=OneNoteHtmlParser(),
        normalizer=OneNoteDocumentNormalizer(),
        chunker=TextChunker(
            settings,
            chunk_size_chars=settings.onenote_chunk_size_chars,
            chunk_overlap_chars=settings.onenote_chunk_overlap_chars,
        ),
        embedder=DeterministicEmbedder(settings),
        metadata_store=PostgresMetadataStore(settings),
        vector_store=QdrantChunkStore(settings, collection_name=settings.onenote_vector_collection),
        resource_hook=NullOneNoteResourceHook(),
    )
