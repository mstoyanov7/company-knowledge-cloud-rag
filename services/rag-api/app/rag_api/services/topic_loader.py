from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from shared_schemas import TopicConfig


class TopicConfigError(ValueError):
    pass


class TopicLoader:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path

    def load(self) -> tuple[TopicConfig, ...]:
        path = self._resolve_path()
        try:
            raw_topics = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise TopicConfigError(f"Topic config file not found: {path}") from error
        except json.JSONDecodeError as error:
            raise TopicConfigError(f"Topic config file is not valid JSON: {path}") from error

        if not isinstance(raw_topics, list):
            raise TopicConfigError("Topic config must be a JSON array.")

        topics = tuple(TopicConfig.model_validate(item) for item in raw_topics)
        self._validate_unique_ids(topics)
        return topics

    def _resolve_path(self) -> Path:
        configured_path = Path(self.config_path)
        if configured_path.is_absolute():
            return configured_path

        candidates = [
            Path.cwd() / configured_path,
            Path(__file__).resolve().parents[5] / configured_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    @staticmethod
    def _validate_unique_ids(topics: Iterable[TopicConfig]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for topic in topics:
            if topic.id in seen:
                duplicates.add(topic.id)
            seen.add(topic.id)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise TopicConfigError(f"Topic config contains duplicate topic ids: {duplicate_list}")
