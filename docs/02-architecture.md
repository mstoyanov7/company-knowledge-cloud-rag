# Architecture

## High-Level Components

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
[Qdrant Vector DB]           [Ollama / OpenAI-compatible model]
   |
   v
[PostgreSQL Metadata DB]

Separate pipeline:

[OneNote Poller / Ops Worker]
   |
   v
[OneNote Graph Connector] --> [Normalizer] --> [Chunker] --> [Embedder] --> [Indexer]
```

## Component Responsibilities

### Open WebUI

- chat interface
- model selection
- optional auth integration
- optional custom pipe / function integration

### RAG API / Orchestrator

- entry point for questions
- validates user identity and tenancy context
- resolves retrieval strategy
- applies source and ACL filters
- calls retriever and reranker
- builds the final LLM prompt
- formats answers with source citations

### OneNote Connector

- fetch notebook, section, and page content from Microsoft Graph
- support delegated auth
- support personal and site-hosted notebook scopes
- expose source metadata without owning indexing logic

### Sync Worker

- normalize OneNote HTML
- compute content hashes
- chunk changed pages
- write metadata to PostgreSQL
- write vectors and payloads to Qdrant
- reconcile removed or moved pages

## Design Principle

Never couple retrieval logic to the chosen LLM provider.
