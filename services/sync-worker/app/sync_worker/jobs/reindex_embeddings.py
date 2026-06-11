from __future__ import annotations

import argparse
import logging

from shared_schemas import get_settings

from sync_worker.ingestion import ChunkEmbedder
from sync_worker.persistence import PostgresMetadataStore, QdrantChunkStore

logger = logging.getLogger("sync_worker.jobs.reindex_embeddings")


def run() -> None:
    """Rebuild the Qdrant vector collection from chunks already stored in Postgres.

    Use this after changing the embedding model (provider, model, or dimension):
    it re-embeds every persisted chunk and re-upserts it, with NO Microsoft Graph
    / OneNote calls — so it sidesteps OneNote API throttling (429) entirely and is
    far faster than a full bootstrap re-crawl.
    """
    parser = argparse.ArgumentParser(description="Re-embed stored chunks into the vector store (no source crawl).")
    parser.add_argument("--batch-size", type=int, default=64, help="Chunks embedded per request batch.")
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    scope_key = settings.onenote_scope_key
    metadata_store = PostgresMetadataStore(settings)
    vector_store = QdrantChunkStore(settings, collection_name=settings.onenote_vector_collection)
    embedder = ChunkEmbedder(settings)

    # Recreate the collection so it matches the current embedding dimension, then
    # repopulate it from the stored chunks.
    vector_store.ensure_collection()

    chunks = metadata_store.list_chunks(scope_key, source_system="onenote")
    if not chunks:
        logger.warning("event=reindex_no_chunks scope=%s provider=%s", scope_key, settings.default_embedding_provider)
        return

    # Stamp the current provider so the stored payload reflects how it was embedded.
    chunks = [chunk.model_copy(update={"embedding_model": settings.default_embedding_provider}) for chunk in chunks]

    batch_size = max(1, args.batch_size)
    written = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embedder.embed_chunks(batch)
        vector_store.upsert_chunks(batch, embeddings)
        written += len(batch)
        logger.info(
            "event=reindex_progress scope=%s written=%s total=%s",
            scope_key,
            written,
            len(chunks),
        )

    logger.info(
        "event=reindex_completed scope=%s provider=%s model=%s vector_size=%s chunks=%s",
        scope_key,
        settings.default_embedding_provider,
        settings.embedding_model_name,
        settings.embedding_vector_size,
        written,
    )


if __name__ == "__main__":
    run()
