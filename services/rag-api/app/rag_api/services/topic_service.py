from __future__ import annotations

from dataclasses import dataclass

from shared_schemas import AnswerRequest, Topic, TopicConfig, UserContext

from rag_api.persistence.app_store import AppDataStore, AppTopicRecord, json_dumps
from rag_api.services.topic_loader import TopicLoader

NO_ALLOWED_SOURCE_FILTER = "__no_allowed_source__"


class TopicNotFoundError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AnswerTopicScope:
    topic: TopicConfig
    user_context: UserContext
    source_filters: list[str]
    retrieval_terms: tuple[str, ...]


class TopicService:
    def __init__(self, loader: TopicLoader | None = None, store: AppDataStore | None = None) -> None:
        self._loader = loader
        self._store = store
        topics = loader.load() if loader is not None else []
        self._topics = {topic.id: topic for topic in topics}
        if self._store is not None and topics:
            self._store.seed_topics_if_empty([_record_from_topic(topic) for topic in topics])

    def list_topics(self, user_context: UserContext | None = None) -> list[Topic]:
        topics = self._topic_configs(enabled_only=True)
        if user_context is None:
            visible_topics = topics
        else:
            user_acl_tags = _normalized_set(user_context.acl_tags)
            visible_topics = [
                topic
                for topic in topics
                if not topic.acl_tags or user_acl_tags.intersection(_normalized_set(topic.acl_tags))
            ]
        return [topic.public_view() for topic in visible_topics]

    def require_topic(self, topic_id: str) -> TopicConfig:
        normalized_topic_id = topic_id.strip()
        topic = self._topic_by_id(normalized_topic_id)
        if topic is None:
            raise TopicNotFoundError(f"Unknown topic_id: {normalized_topic_id}")
        return topic

    def scope_answer_request(self, request: AnswerRequest) -> AnswerTopicScope | None:
        if request.topic_id is None:
            return None

        topic = self.require_topic(request.topic_id)
        user_context = _scope_user_context_to_topic(request.user_context, topic)
        source_filters = _scope_source_filters_to_topic(request.source_filters, topic)
        retrieval_terms = _topic_retrieval_terms(topic)
        return AnswerTopicScope(
            topic=topic,
            user_context=user_context,
            source_filters=source_filters,
            retrieval_terms=retrieval_terms,
        )

    def _topic_configs(self, *, enabled_only: bool) -> list[TopicConfig]:
        if self._store is None:
            return list(self._topics.values())
        return [_topic_from_record(record) for record in self._store.list_topic_records(enabled_only=enabled_only)]

    def _topic_by_id(self, topic_id: str) -> TopicConfig | None:
        if self._store is None:
            return self._topics.get(topic_id)
        record = self._store.get_topic_record(topic_id, enabled_only=True)
        return _topic_from_record(record) if record is not None else None


def _scope_user_context_to_topic(user_context: UserContext, topic: TopicConfig) -> UserContext:
    topic_acl_tags = _normalized_set(topic.acl_tags)
    if not topic_acl_tags:
        return user_context

    user_acl_tags = _normalized_set(user_context.acl_tags)
    allowed_acl_tags = sorted(user_acl_tags.intersection(topic_acl_tags))
    return user_context.model_copy(update={"acl_tags": allowed_acl_tags})


def _scope_source_filters_to_topic(request_filters: list[str], topic: TopicConfig) -> list[str]:
    topic_filters = _normalized_set(topic.source_filters)
    requested_filters = _normalized_set(request_filters)

    if topic_filters and requested_filters:
        scoped_filters = sorted(topic_filters.intersection(requested_filters))
        return scoped_filters or [NO_ALLOWED_SOURCE_FILTER]
    if topic_filters:
        return sorted(topic_filters)
    return sorted(requested_filters)


def _topic_retrieval_terms(topic: TopicConfig) -> tuple[str, ...]:
    values = [
        topic.name,
        *topic.retrieval_tags,
    ]
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _normalized_set(values: list[str]) -> set[str]:
    return {value.strip().lower() for value in values if value.strip()}


def _record_from_topic(topic: TopicConfig) -> AppTopicRecord:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return AppTopicRecord(
        topic_id=topic.id,
        name=topic.name,
        description=topic.description,
        icon=topic.icon,
        acl_tags_json=json_dumps(topic.acl_tags),
        source_filters_json=json_dumps(topic.source_filters),
        retrieval_tags_json=json_dumps(topic.retrieval_tags),
        suggested_questions_json=json_dumps(topic.suggested_questions),
        enabled=True,
        created_at_utc=now,
        updated_at_utc=now,
        updated_by_user_id="seed",
    )


def _topic_from_record(record: AppTopicRecord) -> TopicConfig:
    return TopicConfig(
        id=record.topic_id,
        name=record.name,
        description=record.description,
        icon=record.icon,
        acl_tags=_json_list(record.acl_tags_json),
        source_filters=_json_list(record.source_filters_json),
        retrieval_tags=_json_list(record.retrieval_tags_json),
        suggested_questions=_json_list(record.suggested_questions_json),
    )


def _json_list(value: str | None) -> list[str]:
    import json

    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
