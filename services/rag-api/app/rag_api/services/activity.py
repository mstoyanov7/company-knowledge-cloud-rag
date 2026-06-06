from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from rag_api.persistence.app_store import AppDataStore, FeedbackRecord, QueryLogRecord, json_dumps
from shared_schemas import FeedbackRequest, FeedbackResponse, TrendingQuestion, UserContext


class QueryLogService:
    def __init__(self, *, store: AppDataStore) -> None:
        self.store = store

    def record_question(
        self,
        *,
        question: str,
        topic_id: str | None,
        user_context: UserContext,
    ) -> None:
        normalized = normalize_question(question)
        if not normalized:
            return
        self.store.record_query(
            QueryLogRecord(
                question=question.strip(),
                normalized_question=normalized,
                question_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                topic_id=topic_id,
                user_id=user_context.user_id,
                tenant_id=user_context.tenant_id,
                acl_tags_json=json_dumps(user_context.acl_tags),
                created_at_utc=datetime.now(UTC),
            )
        )

    def trending(
        self,
        *,
        user_context: UserContext,
        window: str,
        limit: int,
    ) -> list[TrendingQuestion]:
        rows = self.store.trending_questions(
            tenant_id=user_context.tenant_id,
            allowed_acl_tags=set(user_context.acl_tags),
            since=datetime.now(UTC) - _window_delta(window),
            limit=max(1, min(limit, 50)),
        )
        return [
            TrendingQuestion(
                question=question,
                topic_id=topic_id,
                count=count,
                unique_users=unique_users,
                last_asked_utc=last_asked_utc,
            )
            for question, topic_id, count, unique_users, last_asked_utc in rows
        ]


class FeedbackService:
    def __init__(self, *, store: AppDataStore) -> None:
        self.store = store

    def create(self, request: FeedbackRequest, user_context: UserContext) -> FeedbackResponse:
        created = self.store.create_feedback(
            FeedbackRecord(
                id=f"fb-{uuid4().hex[:12]}",
                response_id=request.response_id,
                conversation_id=request.conversation_id,
                rating=request.rating,
                flag_gap=request.flag_gap,
                comment=request.comment,
                question=request.question,
                topic_id=request.topic_id,
                user_id=user_context.user_id,
                tenant_id=user_context.tenant_id,
                acl_tags_json=json_dumps(user_context.acl_tags),
                created_at_utc=datetime.now(UTC),
            )
        )
        return _feedback_response(created)

    def list_for_user(self, user_context: UserContext, *, limit: int) -> list[FeedbackResponse]:
        return [
            _feedback_response(record)
            for record in self.store.list_feedback(
                tenant_id=user_context.tenant_id,
                user_id=user_context.user_id,
                limit=max(1, min(limit, 100)),
            )
        ]


def normalize_question(question: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", question.lower()))


def _window_delta(window: str) -> timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([dhw])\s*", window.lower())
    if not match:
        return timedelta(days=30)
    amount = max(1, int(match.group(1)))
    unit = match.group(2)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    return timedelta(days=amount)


def _feedback_response(record: FeedbackRecord) -> FeedbackResponse:
    return FeedbackResponse(
        id=record.id,
        response_id=record.response_id,
        conversation_id=record.conversation_id,
        rating=record.rating,  # type: ignore[arg-type]
        flag_gap=record.flag_gap,
        comment=record.comment,
        question=record.question,
        topic_id=record.topic_id,
        user_id=record.user_id,
        tenant_id=record.tenant_id,
        created_at_utc=record.created_at_utc,
    )

