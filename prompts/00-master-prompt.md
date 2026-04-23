# Master Prompt for Codex

Read all files under `docs/` and `prompts/` before editing code.

Objective:
Build a production-leaning proof of concept for a cloud-hosted enterprise RAG chatbot that uses Open WebUI as the interface, supports model-agnostic LLM providers, ingests SharePoint and OneNote through Microsoft Graph, maintains an incrementally updated retrieval index, and answers with secure citations.

Non-negotiable constraints:
- Open WebUI must remain the frontend and model-selection layer
- retrieval, indexing, sync, citations, and ACL logic must stay in our own backend
- all code must be modular and provider-agnostic
- configuration must be environment-driven
- use Python for backend services
- use FastAPI for the main API
- use PostgreSQL plus a vector store
- keep sync logic separate from query logic
- every retrieved chunk must be traceable to its source
- unauthorized chunks must never be sent to the LLM
- generate code incrementally but keep the repository runnable at every major step

Implementation order:
1. scaffold repository and local infra
2. implement shared schemas and config
3. implement RAG API skeleton
4. implement sync worker skeleton
5. implement SharePoint connector
6. implement OneNote connector
7. implement retrieval, reranking, and citations
8. add observability, retries, and tests

Output rules:
- create code, configs, and README files directly in the repository
- explain assumptions in concise comments or docs
- do not leave placeholder pseudocode where real code can be written
- when a hard dependency is unknown, isolate it behind an interface
- prefer clear structure over premature optimization

After finishing each phase:
- summarize what was created
- list remaining gaps
- propose the next exact coding step
