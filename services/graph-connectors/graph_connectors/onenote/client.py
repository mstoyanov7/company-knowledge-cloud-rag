from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx
from shared_schemas import AppSettings

from graph_connectors.onenote.auth import DelegatedAuthProvider, MockOneNoteDelegatedAuthProvider, MsalDeviceCodeAuthProvider
from graph_connectors.onenote.models import OneNoteNotebook, OneNotePage, OneNoteSection, OneNoteSite


class GraphOneNoteClient(ABC):
    @abstractmethod
    def resolve_site(self) -> OneNoteSite:
        raise NotImplementedError

    @abstractmethod
    def list_notebooks(self, site_id: str) -> list[OneNoteNotebook]:
        raise NotImplementedError

    @abstractmethod
    def list_sections(self, site_id: str) -> list[OneNoteSection]:
        raise NotImplementedError

    @abstractmethod
    def list_pages(
        self,
        site_id: str,
        *,
        modified_since: datetime | None = None,
        next_url: str | None = None,
    ) -> tuple[list[OneNotePage], str | None]:
        raise NotImplementedError

    @abstractmethod
    def get_page_content(self, content_url: str) -> str:
        raise NotImplementedError


class MicrosoftGraphOneNoteClient(GraphOneNoteClient):
    def __init__(
        self,
        settings: AppSettings,
        *,
        auth_provider: DelegatedAuthProvider | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.auth_provider = auth_provider or MsalDeviceCodeAuthProvider(settings)
        self.http_client = http_client or httpx.Client(timeout=60.0)

    def resolve_site(self) -> OneNoteSite:
        if self.settings.resolved_onenote_scope_mode == "me":
            return OneNoteSite(
                id="me",
                name="Personal OneNote",
                web_url="https://www.onenote.com",
                hostname="me",
                relative_path="onenote",
            )
        payload = self._request_json(
            "GET",
            f"/sites/{self.settings.resolved_onenote_site_hostname}:/{self.settings.resolved_onenote_site_scope}",
        )
        return OneNoteSite(
            id=payload["id"],
            name=payload.get("displayName") or payload.get("name") or self.settings.resolved_onenote_site_scope,
            web_url=payload["webUrl"],
            hostname=self.settings.resolved_onenote_site_hostname,
            relative_path=self.settings.resolved_onenote_site_scope,
        )

    def list_notebooks(self, site_id: str) -> list[OneNoteNotebook]:
        payload = self._request_json(
            "GET",
            f"{self._onenote_root(site_id)}/notebooks",
            params={
                "$select": "id,displayName,links,sectionsUrl",
                "$orderby": "displayName asc",
            },
        )
        notebooks: list[OneNoteNotebook] = []
        for raw in payload.get("value", []):
            web_url = (((raw.get("links") or {}).get("oneNoteWebUrl") or {}).get("href")) or raw.get("self") or ""
            notebooks.append(
                OneNoteNotebook(
                    id=raw["id"],
                    display_name=raw.get("displayName") or raw.get("name") or raw["id"],
                    web_url=web_url,
                    sections_url=raw.get("sectionsUrl"),
                )
            )
        return notebooks

    def list_sections(self, site_id: str) -> list[OneNoteSection]:
        payload = self._request_json(
            "GET",
            f"{self._onenote_root(site_id)}/sections",
            params={
                "$select": "id,displayName,links,parentNotebook",
                "$expand": "parentNotebook($select=id,displayName)",
                "$orderby": "displayName asc",
                "$top": "100",
            },
        )
        sections: list[OneNoteSection] = []
        for raw in payload.get("value", []):
            parent_notebook = raw.get("parentNotebook") or {}
            web_url = (((raw.get("links") or {}).get("oneNoteWebUrl") or {}).get("href")) or raw.get("self") or ""
            sections.append(
                OneNoteSection(
                    id=raw["id"],
                    display_name=raw.get("displayName") or raw["id"],
                    notebook_id=parent_notebook.get("id", ""),
                    notebook_name=parent_notebook.get("displayName", ""),
                    web_url=web_url,
                )
            )
        return sections

    def list_pages(
        self,
        site_id: str,
        *,
        modified_since: datetime | None = None,
        next_url: str | None = None,
    ) -> tuple[list[OneNotePage], str | None]:
        if next_url:
            payload = self._request_json("GET", next_url, absolute=True)
        else:
            params = {
                "$select": "id,title,createdDateTime,lastModifiedDateTime,contentUrl,links,level,order,parentNotebook,parentSection",
                "$expand": "parentNotebook($select=id,displayName),parentSection($select=id,displayName)",
                "$orderby": "lastModifiedDateTime asc",
                "$top": str(min(self.settings.onenote_page_page_size, 100)),
            }
            if modified_since:
                params["$filter"] = f"lastModifiedDateTime ge {modified_since.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
            payload = self._request_json("GET", f"{self._onenote_root(site_id)}/pages", params=params)
        pages = [self._parse_page(raw) for raw in payload.get("value", [])]
        return pages, payload.get("@odata.nextLink")

    def get_page_content(self, content_url: str) -> str:
        return self._request_text("GET", content_url, absolute=True, headers={"Accept": "text/html"})

    def _onenote_root(self, site_id: str) -> str:
        if self.settings.resolved_onenote_scope_mode == "me":
            return "/me/onenote"
        return f"/sites/{site_id}/onenote"

    def _parse_page(self, raw: dict[str, Any]) -> OneNotePage:
        parent_notebook = raw.get("parentNotebook") or {}
        parent_section = raw.get("parentSection") or {}
        web_url = (((raw.get("links") or {}).get("oneNoteWebUrl") or {}).get("href")) or raw.get("self") or ""
        return OneNotePage(
            id=raw["id"],
            title=raw.get("title") or "Untitled OneNote Page",
            content_url=raw["contentUrl"],
            web_url=web_url,
            created_utc=_parse_graph_datetime(raw.get("createdDateTime")),
            last_modified_utc=_parse_graph_datetime(raw.get("lastModifiedDateTime")),
            notebook_id=parent_notebook.get("id", ""),
            notebook_name=parent_notebook.get("displayName", ""),
            section_id=parent_section.get("id", ""),
            section_name=parent_section.get("displayName", ""),
            page_level=raw.get("level"),
            page_order=raw.get("order"),
        )

    def _request_json(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, str] | None = None,
        absolute: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(method, path_or_url, params=params, absolute=absolute, headers=headers)
        return response.json()

    def _request_text(
        self,
        method: str,
        path_or_url: str,
        *,
        absolute: bool = False,
        headers: dict[str, str] | None = None,
    ) -> str:
        response = self._request(method, path_or_url, absolute=absolute, headers=headers)
        return response.text

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, str] | None = None,
        absolute: bool = False,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = path_or_url if absolute else _graph_url(self.settings.graph_api_base_url, path_or_url)
        merged_headers = {
            "Authorization": f"Bearer {self.auth_provider.get_access_token()}",
            "Accept": "application/json",
        }
        if headers:
            merged_headers.update(headers)

        last_error: Exception | None = None
        for attempt in range(1, self.settings.onenote_retry_attempts + 1):
            try:
                response = self.http_client.request(method, url, params=params, headers=merged_headers)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.settings.onenote_retry_attempts:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = float(retry_after) if retry_after else self.settings.onenote_retry_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(wait_seconds)
                    continue
                if response.is_error:
                    raise RuntimeError(_format_response_error(method, url, response))
                return response
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt >= self.settings.onenote_retry_attempts:
                    break
                time.sleep(self.settings.onenote_retry_backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError(f"OneNote request failed after retries: {method} {url}") from last_error


class MockOneNoteGraphClient(GraphOneNoteClient):
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        site_scope = settings.resolved_onenote_site_scope
        if settings.resolved_onenote_scope_mode == "me":
            self._site = OneNoteSite(
                id="me",
                name="Personal OneNote",
                web_url="https://www.onenote.com",
                hostname="me",
                relative_path="onenote",
            )
        else:
            self._site = OneNoteSite(
                id="mock-onenote-site",
                name="Onboarding Site",
                web_url=f"https://{settings.resolved_onenote_site_hostname}/{site_scope}",
                hostname=settings.resolved_onenote_site_hostname,
                relative_path=site_scope,
            )
        notebook_specs = (
            [(settings.graph_onenote_notebook_scope, "Orientation")]
            if settings.graph_onenote_notebook_scope
            else [("Team Notebook", "Orientation"), ("Engineering Notebook", "Tooling")]
        )
        self._notebooks: list[OneNoteNotebook] = []
        self._sections: list[OneNoteSection] = []
        self._pages: list[OneNotePage] = []
        self._content: dict[str, str] = {}

        page_templates = {
            "Orientation": [
                (
                    "mock-page-001",
                    "Welcome checklist",
                    datetime(2026, 4, 24, 8, 0, tzinfo=UTC),
                    datetime(2026, 4, 24, 9, 0, tzinfo=UTC),
                    """
                    <html><body>
                    <h1>Day One</h1>
                    <p>Set up your laptop and confirm VPN access.</p>
                    <ul><li>Check payroll setup</li><li>Read the handbook</li></ul>
                    <table><tr><td>Owner</td><td>HR</td></tr><tr><td>ETA</td><td>Day 1</td></tr></table>
                    <img src="https://www.onenote.com/api/v1.0/me/notes/resources/image-1/$value" data-fullres-src="https://www.onenote.com/api/v1.0/resources/image-1/$value" alt="Laptop setup diagram" />
                    </body></html>
                    """,
                ),
                (
                    "mock-page-002",
                    "Benefits notes",
                    datetime(2026, 4, 24, 8, 30, tzinfo=UTC),
                    datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
                    """
                    <html><body>
                    <h2>Benefits</h2>
                    <p>Review medical, leave, and wellness options.</p>
                    <ol><li>Open the portal</li><li>Select your plan</li></ol>
                    <object data="https://www.onenote.com/api/v1.0/me/notes/resources/file-1/$value" data-attachment="benefits.pdf" type="application/pdf"></object>
                    </body></html>
                    """,
                ),
            ],
            "Tooling": [
                (
                    "mock-page-003",
                    "Engineering setup",
                    datetime(2026, 4, 24, 9, 15, tzinfo=UTC),
                    datetime(2026, 4, 24, 10, 30, tzinfo=UTC),
                    """
                    <html><body>
                    <h1>Tool Access</h1>
                    <p>Install the VPN client, IDE, and Git credential manager.</p>
                    <ul><li>VS Code</li><li>Docker Desktop</li><li>Git</li></ul>
                    </body></html>
                    """,
                )
            ],
        }

        for index, (notebook_name, section_name) in enumerate(notebook_specs, start=1):
            notebook_id = f"mock-notebook-{index:03d}"
            section_id = f"mock-section-{index:03d}"
            self._notebooks.append(
                OneNoteNotebook(
                    id=notebook_id,
                    display_name=notebook_name,
                    web_url=f"onenote:https://{settings.resolved_onenote_site_hostname}/{site_scope}/{notebook_name.replace(' ', '%20')}",
                )
            )
            self._sections.append(
                OneNoteSection(
                    id=section_id,
                    display_name=section_name,
                    notebook_id=notebook_id,
                    notebook_name=notebook_name,
                    web_url=f"https://{settings.resolved_onenote_site_hostname}/{site_scope}/{section_name.replace(' ', '%20')}",
                )
            )

            for page_order, (page_id, title, created_utc, modified_utc, html) in enumerate(page_templates[section_name]):
                content_url = f"mock://onenote/pages/{page_id}/content"
                self._pages.append(
                    OneNotePage(
                        id=page_id,
                        title=title,
                        content_url=content_url,
                        web_url=f"https://{settings.resolved_onenote_site_hostname}/{site_scope}/{title.replace(' ', '%20')}",
                        created_utc=created_utc,
                        last_modified_utc=modified_utc,
                        notebook_id=notebook_id,
                        notebook_name=notebook_name,
                        section_id=section_id,
                        section_name=section_name,
                        page_level=0,
                        page_order=page_order,
                    )
                )
                self._content[content_url] = html

    def resolve_site(self) -> OneNoteSite:
        return self._site

    def list_notebooks(self, site_id: str) -> list[OneNoteNotebook]:
        return list(self._notebooks)

    def list_sections(self, site_id: str) -> list[OneNoteSection]:
        return list(self._sections)

    def list_pages(
        self,
        site_id: str,
        *,
        modified_since: datetime | None = None,
        next_url: str | None = None,
    ) -> tuple[list[OneNotePage], str | None]:
        pages = sorted(self._pages, key=lambda page: page.last_modified_utc)
        if modified_since:
            pages = [page for page in pages if page.last_modified_utc >= modified_since]
        return pages, None

    def get_page_content(self, content_url: str) -> str:
        return self._content[content_url]


def build_onenote_auth_provider(settings: AppSettings) -> DelegatedAuthProvider:
    if settings.onenote_graph_mode == "live":
        return MsalDeviceCodeAuthProvider(settings)
    return MockOneNoteDelegatedAuthProvider()


def _parse_graph_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _graph_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _format_response_error(method: str, url: str, response: httpx.Response) -> str:
    response_body = response.text.strip()
    if len(response_body) > 1000:
        response_body = f"{response_body[:1000]}..."
    return (
        "OneNote request failed: "
        f"{method} {url} returned HTTP {response.status_code} {response.reason_phrase}. "
        f"Response body: {response_body or '<empty>'}"
    )
