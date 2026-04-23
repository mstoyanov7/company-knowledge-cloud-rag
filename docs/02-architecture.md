# Architecture

## High-level components

```text
[User]
   |
   v
[Open WebUI]
   |
   v
[RAG API / Orchestrator]
   |------------------------------|
   |                              |
   v                              v
[Retriever]                  [LLM Provider Adapter]
   |                              |
   v                              v
[Vector DB]                  [OpenAI / Azure / Ollama / other]
   |
   v
[Metadata DB + Object Storage]

Separate pipeline:

[Graph Sync Scheduler]
   |
   v
[SharePoint Connector] ----\
                            --> [Normalizer] --> [Chunker] --> [Embedder] --> [Indexer]
[OneNote Connector] -------/
```

## Component responsibilities

### Open WebUI

- chat interface
- model selection
- API key based provider usage
- optional auth integration
- optional custom pipe / function integration

### RAG API / Orchestrator

- entry point for questions
- validates user identity and tenancy context
- resolves retrieval strategy
- applies source and ACL filters
- calls retriever and reranker
- builds the final LLM prompt
- formats answer with citations

### Graph Connectors

- fetch source content from Microsoft Graph
- store raw source snapshots and metadata
- support incremental sync
- emit indexing jobs

### Normalizer

Convert all source types to a common internal schema.

### Chunker

Split content into retrieval-friendly units while preserving source traceability.

### Embedder

Generate embeddings with a configurable model.

### Indexer

Write vectors, metadata, hashes, and source references.

### Retriever

Support hybrid search:

- semantic search
- keyword / metadata search
- source filtering
- ACL filtering

### Reranker

Improve top-k relevance before prompt construction.

### Metadata DB

Store:

- source inventory
- sync checkpoints
- chunk metadata
- access tags
- content hashes
- job states
- citations

### Object Storage

Store:

- normalized text snapshots
- extracted file content
- optional previews
- optional chunk debug artifacts

## Design principle

Never couple retrieval logic to the chosen LLM provider.
