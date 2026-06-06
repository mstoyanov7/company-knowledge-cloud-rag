from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path

from shared_schemas import AppSettings, TopicConfig

from graph_connectors.onenote.models import OneNotePage


@dataclass(frozen=True, slots=True)
class OneNoteTopicClassification:
    topic_ids: tuple[str, ...]
    confidence: dict[str, float]
    matched_terms: dict[str, tuple[str, ...]]
    tags: tuple[str, ...]


class OneNoteTopicClassifier:
    def __init__(self, topics: tuple[TopicConfig, ...]) -> None:
        self.topics = topics

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "OneNoteTopicClassifier":
        return cls(_load_topics(settings.topics_config_path))

    def classify(self, *, page: OneNotePage, content_text: str) -> OneNoteTopicClassification:
        title = _normalized_text(page.title)
        section = _normalized_text(page.section_name)
        notebook = _normalized_text(page.notebook_name)
        content = _normalized_text(content_text)

        scored: list[tuple[int, str, tuple[str, ...]]] = []
        for topic in self.topics:
            score = 0
            matched_terms: list[str] = []
            for term in _topic_terms(topic):
                normalized_term = _normalized_text(term)
                if not normalized_term:
                    continue
                if _contains_term(title, normalized_term):
                    score += 5
                elif _contains_term(section, normalized_term):
                    score += 4
                elif _contains_term(notebook, normalized_term):
                    score += 2
                elif _contains_term(content, normalized_term):
                    score += 1
                else:
                    continue
                matched_terms.append(term)

            if score >= 2:
                scored.append((score, topic.id, tuple(dict.fromkeys(matched_terms))))

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[:3]
        topic_ids = tuple(topic_id for _score, topic_id, _terms in selected)
        confidence = {topic_id: min(0.99, round(score / 10, 2)) for score, topic_id, _terms in selected}
        matched = {topic_id: terms for _score, topic_id, terms in selected}
        tags = tuple(dict.fromkeys(tag for topic_id in topic_ids for tag in (topic_id, f"topic:{topic_id}")))
        return OneNoteTopicClassification(
            topic_ids=topic_ids,
            confidence=confidence,
            matched_terms=matched,
            tags=tags,
        )


def _load_topics(config_path: str) -> tuple[TopicConfig, ...]:
    path = _resolve_config_path(config_path)
    try:
        raw_topics = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()
    if not isinstance(raw_topics, list):
        return ()
    return tuple(TopicConfig.model_validate(topic) for topic in raw_topics)


def _resolve_config_path(config_path: str) -> Path:
    configured = Path(config_path)
    if configured.is_absolute():
        return configured
    candidates = [
        Path.cwd() / configured,
        Path(__file__).resolve().parents[5] / configured,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _topic_terms(topic: TopicConfig) -> tuple[str, ...]:
    values = [
        topic.id.replace("-", " "),
        topic.name,
        *topic.retrieval_tags,
    ]
    return tuple(dict.fromkeys(value.strip().lower() for value in values if value.strip()))


def _normalized_text(value: str) -> str:
    words = re.findall(r"[^\W_]+", value.lower())
    return " ".join(_normalize_token(word) for word in words)


def _contains_term(haystack: str, term: str) -> bool:
    if not haystack or not term:
        return False
    return f" {term} " in f" {haystack} "


def _normalize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token
