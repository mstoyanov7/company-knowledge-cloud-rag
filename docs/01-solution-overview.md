# Solution Overview

## Problem

Company onboarding knowledge in this project is maintained in OneNote notebooks.
Newcomers waste time searching manually, and answers become outdated when notes change.

## Proposed solution

Build a Cloud-RAG system behind Open WebUI.

The user interacts with Open WebUI. Open WebUI sends the question to a custom
FastAPI backend. The backend retrieves relevant OneNote chunks from a continuously
updated index, builds a grounded prompt, and generates an answer through a
model-agnostic LLM adapter.

## Main requirements

### Functional

- connect to OneNote through Microsoft Graph
- fetch and normalize notebook, section, and page content
- index OneNote content in Qdrant
- answer questions with source-title citations
- support multiple OpenAI-compatible LLM providers
- refresh the index incrementally

### Non-functional

- low retrieval latency
- secure by default
- explainable via source citations
- resilient to API failures and throttling
- maintainable as a company service

## Boundary of responsibility

### Open WebUI should do

- user authentication if integrated that way
- chat UI
- chat history
- model selection
- sending prompts to the backend

### The backend should do

- OneNote sync
- parsing and chunking
- embedding
- indexing
- metadata and ACL handling
- retrieval
- reranking
- prompt building
- citation generation
- freshness handling

## Recommended architectural style

Use scheduled synchronization:

- fast incremental polling for changed pages
- lookback hash checks to catch timestamp drift
- reconciliation to repair missed deletes or moved pages
