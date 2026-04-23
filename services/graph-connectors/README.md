# Graph Connectors

This package defines the source-specific boundary for Microsoft Graph ingestion.

Phase 2 adds the SharePoint Graph integration boundary:

- `graph_connectors.sharepoint.auth.ClientCredentialsTokenProvider`
- `graph_connectors.sharepoint.client.MicrosoftGraphSharePointClient`
- `graph_connectors.sharepoint.client.MockSharePointGraphClient`
- `graph_connectors.sharepoint.connector.SharePointConnector`

The connector resolves the configured site and document library scope, while the
worker owns extraction, normalization, hashing, chunking, and indexing.

Phase 3 adds a separate OneNote boundary:

- `graph_connectors.onenote.auth.DelegatedAuthProvider`
- `graph_connectors.onenote.auth.MsalDeviceCodeAuthProvider`
- `graph_connectors.onenote.client.MicrosoftGraphOneNoteClient`
- `graph_connectors.onenote.client.MockOneNoteGraphClient`
- `graph_connectors.onenote.connector.OneNoteConnector`

OneNote authentication is delegated-only in this repository. The connector targets
site-hosted team notebooks via `/sites/{site-id}/onenote` endpoints.
