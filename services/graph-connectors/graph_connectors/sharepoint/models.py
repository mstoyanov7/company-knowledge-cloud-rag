from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SharePointSite(BaseModel):
    id: str
    name: str
    web_url: str
    hostname: str
    relative_path: str


class SharePointDrive(BaseModel):
    id: str
    name: str
    web_url: str
    drive_type: str = "documentLibrary"


class SharePointDriveItem(BaseModel):
    id: str
    name: str
    web_url: str
    parent_path: str | None = None
    file_name: str
    file_extension: str = ""
    mime_type: str | None = None
    size: int | None = None
    is_file: bool = False
    is_deleted: bool = False
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    e_tag: str | None = None
    c_tag: str | None = None
    acl_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SharePointDeltaPage(BaseModel):
    items: list[SharePointDriveItem]
    next_link: str | None = None
    delta_link: str | None = None
