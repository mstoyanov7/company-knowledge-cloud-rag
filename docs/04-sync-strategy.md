# Sync Strategy

## Objective

Keep the OneNote RAG index fresh without reprocessing everything every time.

## OneNote Strategy

Use notebook / section / page scheduled polling with checkpoints.

Recommended approach:

- store the latest processed page modification cursor
- list changed pages by modification time
- use a configurable lookback window to re-check recent pages by content hash
- fetch only relevant page HTML
- re-chunk and reindex only when content hash changes
- run reconciliation to catch deleted or moved pages

## Scheduler Model

Jobs:

- `onenote_bootstrap`
- `onenote_incremental`
- `onenote_reconciliation`
- `ops_worker`
- failed-job retry worker

## Failure Handling

For every connector job:

- use exponential backoff
- mark terminal failures after retry limit
- send failed items to dead-letter storage
- keep health metrics

## Freshness SLA Proposal

For the diploma prototype:

- OneNote edits visible in the index after the next polling cycle when Microsoft Graph exposes the updated page
- deleted or moved pages cleaned by reconciliation
- full reconciliation once per day, or faster for small notebooks
