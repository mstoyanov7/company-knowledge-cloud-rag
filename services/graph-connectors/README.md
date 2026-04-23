# Graph Connectors

This package defines the source-specific boundary for Microsoft Graph ingestion.

Phase 1 intentionally keeps connectors minimal:

- `graph_connectors.sharepoint.SharePointConnector`
- `graph_connectors.onenote.OneNoteConnector`

Each connector only exposes scope and scheduling metadata so later phases can add
real Graph clients without mixing connector concerns into retrieval or API code.
