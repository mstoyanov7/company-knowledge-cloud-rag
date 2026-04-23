# Codex Prompt - Phase 3 OneNote Connector

Goal:
Implement OneNote ingestion with incremental polling.

Tasks:
- create a Graph client wrapper for OneNote notebooks, sections, and pages
- create a connector service that traverses notebooks in a restricted onboarding scope
- fetch page content and metadata
- normalize page content into the shared document schema
- compute content hashes
- chunk and index only changed pages
- store notebook or page checkpoints for incremental polling
- add job entrypoints for `onenote_bootstrap` and `onenote_incremental`
- add tests for page normalization and checkpoint behavior

Important constraints:
- keep authentication details isolated behind an auth provider interface
- keep fetched page data traceable to notebook, section, and page
- preserve source URLs and last modified timestamps
- do not mix retrieval logic into connector code

Definition of done:
- a limited OneNote scope can be ingested
- changed pages are reindexed without full rebuild
- citations can point back to original pages
