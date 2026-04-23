from datetime import UTC, datetime

from pydantic import BaseModel, Field


class OneNoteSite(BaseModel):
    id: str
    name: str
    web_url: str
    hostname: str
    relative_path: str


class OneNoteNotebook(BaseModel):
    id: str
    display_name: str
    web_url: str
    sections_url: str | None = None


class OneNoteSection(BaseModel):
    id: str
    display_name: str
    notebook_id: str
    notebook_name: str
    web_url: str


class OneNotePage(BaseModel):
    id: str
    title: str
    content_url: str
    web_url: str
    created_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_modified_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notebook_id: str
    notebook_name: str
    section_id: str
    section_name: str
    page_level: int | None = None
    page_order: int | None = None
