# Graph Connectors

This package defines the Microsoft Graph boundary for OneNote ingestion.

The OneNote connector exposes:

- `graph_connectors.onenote.auth.DelegatedAuthProvider`
- `graph_connectors.onenote.auth.MsalDeviceCodeAuthProvider`
- `graph_connectors.onenote.client.MicrosoftGraphOneNoteClient`
- `graph_connectors.onenote.client.MockOneNoteGraphClient`
- `graph_connectors.onenote.connector.OneNoteConnector`

OneNote authentication is delegated-only in this repository. The connector can
target personal notebooks through `/me/onenote` or site-hosted team notebooks
through `/sites/{site-id}/onenote`. Indexing, normalization, hashing, chunking,
and vector writes stay in `sync-worker`.
