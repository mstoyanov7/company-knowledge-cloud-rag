# Data Flow

## Ingestion flow

1. connector fetches source item
2. raw source metadata is stored
3. item content is normalized to plain text / markdown-like structure
4. content hash is computed
5. unchanged items are skipped
6. changed items are chunked
7. each chunk gets stable metadata
8. embeddings are generated
9. chunks are written to vector DB
10. source checkpoints are updated

## Query flow

1. user submits question in Open WebUI
2. Open WebUI sends question and user context to RAG API
3. RAG API resolves allowed sources and filters
4. retriever runs hybrid search
5. reranker refines the top results
6. prompt builder creates a citation-aware prompt
7. selected LLM generates answer
8. response formatter returns:
   - answer
   - citations
   - source links
   - freshness timestamp
   - optional confidence signals

## Internal document schema

Use a common chunk schema like:

- `tenant_id`
- `source_system`
- `source_container`
- `source_item_id`
- `source_url`
- `title`
- `section_path`
- `last_modified_utc`
- `acl_tags`
- `content_hash`
- `chunk_id`
- `chunk_index`
- `chunk_text`
- `embedding_model`
- `language`
- `tags`

## Citation rule

Every chunk returned to the LLM must be traceable to:

- original source item
- chunk index
- human-readable title/path
- source URL
- last modified timestamp
