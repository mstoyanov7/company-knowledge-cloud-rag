from __future__ import annotations

from dataclasses import dataclass

from shared_schemas import AnswerRequest, Topic, TopicConfig, UserContext

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
    def __init__(self, loader: TopicLoader) -> None:
        topics = loader.load()
        self._topics = {topic.id: topic for topic in topics}

    def list_topics(self, user_context: UserContext | None = None) -> list[Topic]:
        if user_context is None:
            visible_topics = self._topics.values()
        else:
            user_acl_tags = _normalized_set(user_context.acl_tags)
            visible_topics = [
                topic
                for topic in self._topics.values()
                if not topic.acl_tags or user_acl_tags.intersection(_normalized_set(topic.acl_tags))
            ]
        return [topic.public_view() for topic in visible_topics]

    def require_topic(self, topic_id: str) -> TopicConfig:
        normalized_topic_id = topic_id.strip()
        topic = self._topics.get(normalized_topic_id)
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
