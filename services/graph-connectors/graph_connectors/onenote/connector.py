from shared_schemas.config import AppSettings

from graph_connectors.base import ConnectorBase


class OneNoteConnector(ConnectorBase):
    connector_name = "onenote"

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)

    def describe_scope(self) -> str:
        scope = self.settings.graph_onenote_scope or "mock-onenote-onboarding-notebook"
        return f"OneNote onboarding scope: {scope}"

    def sync_interval_seconds(self) -> int:
        return self.settings.onenote_sync_interval_seconds
