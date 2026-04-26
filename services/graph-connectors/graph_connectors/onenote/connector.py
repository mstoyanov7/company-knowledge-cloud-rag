from shared_schemas.config import AppSettings

from graph_connectors.base import ConnectorBase
from graph_connectors.onenote.client import GraphOneNoteClient, MicrosoftGraphOneNoteClient, MockOneNoteGraphClient
from graph_connectors.onenote.models import OneNoteNotebook, OneNoteSection, OneNoteSite


class OneNoteConnector(ConnectorBase):
    connector_name = "onenote"

    def __init__(self, settings: AppSettings, client: GraphOneNoteClient | None = None) -> None:
        super().__init__(settings)
        self.client = client or self._build_client()

    def describe_scope(self) -> str:
        notebook_scope = self.settings.graph_onenote_notebook_scope or "all notebooks"
        if self.settings.resolved_onenote_scope_mode == "me":
            return f"OneNote personal scope: /me/onenote notebook={notebook_scope}"
        return (
            "OneNote onboarding scope: "
            f"{self.settings.resolved_onenote_site_hostname}/{self.settings.resolved_onenote_site_scope} "
            f"notebook={notebook_scope}"
        )

    def sync_interval_seconds(self) -> int:
        return self.settings.onenote_sync_interval_seconds

    def resolve_scope(self) -> tuple[OneNoteSite, list[OneNoteNotebook], list[OneNoteSection]]:
        site = self.client.resolve_site()
        notebooks = self.client.list_notebooks(site.id)
        if self.settings.graph_onenote_notebook_scope:
            notebooks = [
                notebook
                for notebook in notebooks
                if notebook.display_name == self.settings.graph_onenote_notebook_scope
            ]
        if not notebooks:
            raise ValueError(
                f"Configured OneNote notebook scope '{self.settings.graph_onenote_notebook_scope or 'all notebooks'}' "
                f"returned no notebooks for site {site.id}."
            )
        sections = [
            section
            for section in self.client.list_sections(site.id)
            if section.notebook_id in {notebook.id for notebook in notebooks}
        ]
        return site, notebooks, sections

    def _build_client(self) -> GraphOneNoteClient:
        if self.settings.onenote_graph_mode == "live":
            return MicrosoftGraphOneNoteClient(self.settings)
        return MockOneNoteGraphClient(self.settings)
