from shared_schemas import AppSettings
from shared_schemas.embeddings import Embedder, create_embedder


def build_query_embedder(settings: AppSettings) -> Embedder:
    """Query-side embedder. Resolves through the shared factory so query vectors
    always come from the same model and dimension as the indexed chunk vectors."""
    return create_embedder(settings)
