from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from shared_schemas import AppSettings

from graph_connectors.sharepoint.auth import ClientCredentialsTokenProvider
from graph_connectors.sharepoint.models import SharePointDeltaPage, SharePointDrive, SharePointDriveItem, SharePointSite


class GraphSharePointClient(ABC):
    @abstractmethod
    def resolve_site(self) -> SharePointSite:
        raise NotImplementedError

    @abstractmethod
    def list_drives(self, site_id: str) -> list[SharePointDrive]:
        raise NotImplementedError

    @abstractmethod
    def get_drive_delta_page(
        self,
        drive_id: str,
        *,
        cursor_url: str | None = None,
        delta_link: str | None = None,
    ) -> SharePointDeltaPage:
        raise NotImplementedError

    @abstractmethod
    def download_file(self, drive_id: str, item_id: str) -> bytes:
        raise NotImplementedError


class MicrosoftGraphSharePointClient(GraphSharePointClient):
    def __init__(
        self,
        settings: AppSettings,
        *,
        token_provider: ClientCredentialsTokenProvider | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.Client(timeout=60.0, follow_redirects=True)
        self.token_provider = token_provider or ClientCredentialsTokenProvider(settings)

    def resolve_site(self) -> SharePointSite:
        payload = self._get(f"/sites/{self.settings.graph_sharepoint_hostname}:/{self.settings.graph_sharepoint_site_scope}")
        return SharePointSite(
            id=payload["id"],
            name=payload.get("displayName") or payload.get("name") or self.settings.graph_sharepoint_site_scope,
            web_url=payload["webUrl"],
            hostname=self.settings.graph_sharepoint_hostname,
            relative_path=self.settings.graph_sharepoint_site_scope,
        )

    def list_drives(self, site_id: str) -> list[SharePointDrive]:
        payload = self._get(f"/sites/{site_id}/drives")
        drives: list[SharePointDrive] = []
        for raw_drive in payload.get("value", []):
            drives.append(
                SharePointDrive(
                    id=raw_drive["id"],
                    name=raw_drive["name"],
                    web_url=raw_drive["webUrl"],
                    drive_type=raw_drive.get("driveType", "documentLibrary"),
                )
            )
        return drives

    def get_drive_delta_page(
        self,
        drive_id: str,
        *,
        cursor_url: str | None = None,
        delta_link: str | None = None,
    ) -> SharePointDeltaPage:
        if cursor_url:
            payload = self._get_absolute(cursor_url)
        elif delta_link:
            payload = self._get_absolute(delta_link)
        else:
            payload = self._get(
                f"/drives/{drive_id}/root/delta",
                params={
                    "$top": str(self.settings.sharepoint_delta_page_size),
                },
                extra_headers={"deltaExcludeParent": "true"},
            )
        return self._parse_delta_page(payload)

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        response = self.http_client.get(
            urljoin(self.settings.graph_api_base_url, f"/drives/{drive_id}/items/{item_id}/content"),
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.content

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_provider.get_access_token()}",
            "Accept": "application/json",
        }

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        response = self.http_client.get(urljoin(self.settings.graph_api_base_url, path), params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    def _get_absolute(self, url: str) -> dict[str, Any]:
        response = self.http_client.get(url, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _parse_delta_page(self, payload: dict[str, Any]) -> SharePointDeltaPage:
        items: list[SharePointDriveItem] = []
        for raw_item in payload.get("value", []):
            file_name = raw_item.get("name") or raw_item["id"]
            file_extension = ""
            if "." in file_name:
                file_extension = file_name.rsplit(".", maxsplit=1)[1].lower()

            parent_reference = raw_item.get("parentReference") or {}
            file_facet = raw_item.get("file") or {}
            items.append(
                SharePointDriveItem(
                    id=raw_item["id"],
                    name=file_name,
                    web_url=raw_item.get("webUrl", ""),
                    parent_path=parent_reference.get("path"),
                    file_name=file_name,
                    file_extension=file_extension,
                    mime_type=file_facet.get("mimeType"),
                    size=raw_item.get("size"),
                    is_file=bool(file_facet),
                    is_deleted="deleted" in raw_item,
                    last_modified_utc=_parse_graph_datetime(raw_item.get("lastModifiedDateTime")),
                    e_tag=raw_item.get("eTag"),
                    c_tag=raw_item.get("cTag"),
                    metadata={
                        "parent_reference": parent_reference,
                        "download_url": raw_item.get("@microsoft.graph.downloadUrl"),
                    },
                )
            )
        return SharePointDeltaPage(
            items=items,
            next_link=payload.get("@odata.nextLink"),
            delta_link=payload.get("@odata.deltaLink"),
        )


class MockSharePointGraphClient(GraphSharePointClient):
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._site = SharePointSite(
            id="mock-site-onboarding",
            name="Onboarding Site",
            web_url="https://contoso.sharepoint.com/sites/onboarding",
            hostname=settings.graph_sharepoint_hostname,
            relative_path=settings.graph_sharepoint_site_scope,
        )
        self._drive = SharePointDrive(
            id="mock-drive-documents",
            name=settings.graph_sharepoint_drive_scope,
            web_url="https://contoso.sharepoint.com/sites/onboarding/shared%20documents",
        )
        self._pages = {
            "bootstrap": SharePointDeltaPage(
                items=[
                    SharePointDriveItem(
                        id="mock-item-001",
                        name="day1-checklist.txt",
                        web_url=f"{self._drive.web_url}/day1-checklist.txt",
                        parent_path="/drive/root:/General",
                        file_name="day1-checklist.txt",
                        file_extension="txt",
                        mime_type="text/plain",
                        size=128,
                        is_file=True,
                        last_modified_utc=datetime(2026, 4, 24, tzinfo=UTC),
                        metadata={"download_url": "mock://day1-checklist.txt"},
                    ),
                    SharePointDriveItem(
                        id="mock-item-002",
                        name="benefits-guide.txt",
                        web_url=f"{self._drive.web_url}/benefits-guide.txt",
                        parent_path="/drive/root:/General",
                        file_name="benefits-guide.txt",
                        file_extension="txt",
                        mime_type="text/plain",
                        size=164,
                        is_file=True,
                        last_modified_utc=datetime(2026, 4, 24, tzinfo=UTC),
                        metadata={"download_url": "mock://benefits-guide.txt"},
                    ),
                ],
                next_link=None,
                delta_link="mock://delta/bootstrap-complete",
            ),
            "incremental": SharePointDeltaPage(
                items=[],
                next_link=None,
                delta_link="mock://delta/bootstrap-complete",
            ),
        }
        self._content = {
            "mock-item-001": (
                "On day one, new hires should connect to the VPN, confirm laptop setup, "
                "complete payroll forms, and review the onboarding handbook."
            ).encode("utf-8"),
            "mock-item-002": (
                "Benefits enrollment opens during the first week. Employees should review health "
                "coverage, paid leave, and the wellness portal setup steps."
            ).encode("utf-8"),
        }

    def resolve_site(self) -> SharePointSite:
        return self._site

    def list_drives(self, site_id: str) -> list[SharePointDrive]:
        return [self._drive]

    def get_drive_delta_page(
        self,
        drive_id: str,
        *,
        cursor_url: str | None = None,
        delta_link: str | None = None,
    ) -> SharePointDeltaPage:
        if delta_link:
            return self._pages["incremental"]
        return self._pages["bootstrap"]

    def download_file(self, drive_id: str, item_id: str) -> bytes:
        return self._content[item_id]


def _parse_graph_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(UTC)
