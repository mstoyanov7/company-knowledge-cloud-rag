from shared_schemas.config import AppSettings

from graph_connectors.base import ConnectorBase
from graph_connectors.sharepoint.client import (
    GraphSharePointClient,
    MockSharePointGraphClient,
    MicrosoftGraphSharePointClient,
)
from graph_connectors.sharepoint.models import SharePointDrive, SharePointSite


class SharePointConnector(ConnectorBase):
    connector_name = "sharepoint"

    def __init__(self, settings: AppSettings, client: GraphSharePointClient | None = None) -> None:
        super().__init__(settings)
        self.client = client or self._build_client()

    def describe_scope(self) -> str:
        return (
            "SharePoint onboarding scope: "
            f"{self.settings.graph_sharepoint_hostname}/{self.settings.graph_sharepoint_site_scope} "
            f"library={self.settings.graph_sharepoint_drive_scope}"
        )

    def sync_interval_seconds(self) -> int:
        return self.settings.sharepoint_sync_interval_seconds

    def resolve_scope(self) -> tuple[SharePointSite, SharePointDrive]:
        site = self.client.resolve_site()
        drives = self.client.list_drives(site.id)
        for drive in drives:
            if drive.name == self.settings.graph_sharepoint_drive_scope:
                return site, drive
        raise ValueError(
            f"Configured SharePoint library '{self.settings.graph_sharepoint_drive_scope}' was not found for site {site.id}."
        )

    def _build_client(self) -> GraphSharePointClient:
        if self.settings.sharepoint_graph_mode == "live":
            return MicrosoftGraphSharePointClient(self.settings)
        return MockSharePointGraphClient(self.settings)
