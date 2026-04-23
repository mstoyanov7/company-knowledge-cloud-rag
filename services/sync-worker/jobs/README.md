# Sync Worker Jobs

This directory contains the runnable SharePoint job entrypoints:

- `sharepoint_bootstrap`
- `sharepoint_incremental`
- `onenote_bootstrap`
- `onenote_incremental`

The current implementation runs in-process so the repository stays runnable
without an external queue framework.
