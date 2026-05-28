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
