# Codex Prompt - Phase 4 Answer Engine

Goal:
Implement secure retrieval and answer generation.

Tasks:
- create a query endpoint in `rag-api`
- accept question, user identity context, source filters, and optional provider selection
- implement metadata filtering and ACL filtering
- implement hybrid retrieval abstraction
- implement reranker abstraction
- create prompt builder that includes:
  - system instruction
  - user question
  - selected chunks
  - citation markers
- create answer formatter that returns:
  - answer text
  - citations
  - source titles
  - source URLs
  - freshness timestamps
- ensure unauthorized chunks never reach the prompt builder
- add tests for ACL filtering and citation formatting
- add a mock provider plus one real provider adapter behind config

Important constraints:
- prompt building must be independent of the provider implementation
- retrieval must be deterministic enough for testing
- citations must be based on actual selected chunks, not invented references

Definition of done:
- a user can ask a question
- the system retrieves allowed chunks
- the model returns a cited answer
- the response schema is stable and testable
