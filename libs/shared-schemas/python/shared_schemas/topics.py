from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Topic(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    icon: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)


class TopicConfig(Topic):
    acl_tags: list[str] = Field(default_factory=list)
    source_filters: list[str] = Field(default_factory=list)
    retrieval_tags: list[str] = Field(default_factory=list)

    def public_view(self) -> Topic:
        return Topic(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            suggested_questions=list(self.suggested_questions),
        )


class TopicAdmin(TopicConfig):
    enabled: bool = True
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by_user_id: str | None = None


class TopicCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    icon: str | None = Field(default=None, max_length=80)
    acl_tags: list[str] = Field(default_factory=list)
    source_filters: list[str] = Field(default_factory=list)
    retrieval_tags: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    enabled: bool = True


class TopicUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    icon: str | None = Field(default=None, max_length=80)
    acl_tags: list[str] | None = None
    source_filters: list[str] | None = None
    retrieval_tags: list[str] | None = None
    suggested_questions: list[str] | None = None
    enabled: bool | None = None


class UiSettings(BaseModel):
    app_name: str = "Company Knowledge"
    app_subtitle: str = "Assistant"
    accent_hue: int = Field(default=45, ge=0, le=360)
    logo_url: str | None = None
    logo_text: str | None = None
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by_user_id: str | None = None


class UiSettingsUpdate(BaseModel):
    app_name: str | None = Field(default=None, min_length=1, max_length=120)
    app_subtitle: str | None = Field(default=None, max_length=200)
    accent_hue: int | None = Field(default=None, ge=0, le=360)
    logo_url: str | None = Field(default=None, max_length=500)
    logo_text: str | None = Field(default=None, max_length=20)
