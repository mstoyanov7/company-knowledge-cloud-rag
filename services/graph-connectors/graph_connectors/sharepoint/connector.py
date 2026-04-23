from shared_schemas.config import AppSettings

from graph_connectors.base import ConnectorBase


class SharePointConnector(ConnectorBase):
    connector_name = "sharepoint"

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)

    def describe_scope(self) -> str:
        scope = self.settings.graph_sharepoint_scope or "mock-sharepoint-onboarding-site"
        return f"SharePoint onboarding scope: {scope}"

    def sync_interval_seconds(self) -> int:
        return self.settings.sharepoint_sync_interval_seconds
