# Sync Strategy

## Objective

Keep the cloud RAG index fresh without reprocessing everything every time.

## SharePoint strategy

Use three layers:

### 1. Initial full crawl
Used once for bootstrap.

### 2. Incremental sync
Use source-native change tracking where possible.
Store delta checkpoints per site / drive / library.

### 3. Nightly reconciliation
Re-scan scope boundaries to repair drift, missed events, or failed jobs.

## OneNote strategy

Use notebook / section / page level scheduled polling with checkpoints.

Recommended approach:

- store per-notebook checkpoint
- list changed pages by modification time or equivalent change marker
- fetch only changed pages
- re-chunk and reindex only when content hash changes

## Scheduler model

Have at least these jobs:

- `bootstrap_job`
- `sharepoint_incremental_job`
- `onenote_incremental_job`
- `subscription_renewal_job`
- `nightly_reconciliation_job`
- `failed_job_retry_worker`
- `orphan_cleanup_job`

## Failure handling

For every connector job:

- use exponential backoff
- mark terminal failures after retry limit
- send failed items to dead-letter storage
- keep per-source health metrics

## Freshness SLA proposal

For the diploma prototype, define a target such as:

- SharePoint updates visible in index within 1 to 5 minutes
- OneNote updates visible in index within 5 to 15 minutes
- full reconciliation once per day

Adjust after measurement.
