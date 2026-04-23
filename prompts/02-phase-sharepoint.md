# Codex Prompt - Phase 2 SharePoint Connector

Goal:
Implement SharePoint ingestion with bootstrap crawl and incremental sync.

Tasks:
- create a Graph client wrapper for SharePoint-related operations
- create config for tenant id, client id, client secret or equivalent secret management placeholders, site scope, and sync intervals
- implement site and library discovery for a restricted onboarding scope
- fetch files and metadata from the selected scope
- add a file extraction pipeline abstraction
- normalize extracted content into the shared document schema
- compute content hashes
- skip unchanged items
- chunk changed items
- write chunks to the vector store and metadata DB
- store checkpoints for incremental sync
- implement a job entrypoint for `sharepoint_bootstrap` and `sharepoint_incremental`
- add structured logs for every major step
- add tests for hashing, normalization, and checkpoint updates

Important constraints:
- keep SharePoint connector code isolated from the indexing pipeline
- connector returns source objects, then normalizer and indexer handle the rest
- do not hardcode Graph response shapes outside the client layer

Definition of done:
- a restricted SharePoint scope can be crawled
- items can be normalized and indexed
- unchanged items are skipped
- incremental sync updates only changed content
