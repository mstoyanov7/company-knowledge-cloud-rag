from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from shared_schemas import AppSettings


class AppStoreConflict(ValueError):
    pass


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "app_users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    acl_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    groups_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dept: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    app_role: Mapped[str] = mapped_column(String(32), nullable=False, default="user", server_default="user", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SessionRecord(Base):
    __tablename__ = "app_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), index=True)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueryLogRecord(Base):
    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    acl_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    flag_gap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    topic_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    acl_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class AppTopicRecord(Base):
    __tablename__ = "app_topics"

    topic_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acl_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_filters_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    section_filters_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    retrieval_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    suggested_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    section_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    auto_managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1", index=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UiSettingsRecord(Base):
    __tablename__ = "ui_settings"

    settings_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_name: Mapped[str] = mapped_column(String(120), nullable=False)
    app_subtitle: Mapped[str] = mapped_column(String(200), nullable=False)
    accent_hue: Mapped[int] = mapped_column(Integer, nullable=False, default=45, server_default="45")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_text: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AppDataStore:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._ensure_sqlite_directory(settings.app_database_url)
        connect_args = {"check_same_thread": False} if settings.app_database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.app_database_url, future=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def ensure_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_compat_columns()

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def create_user(self, record: UserRecord) -> UserRecord:
        with self.session() as session:
            session.add(record)
            try:
                session.flush()
            except IntegrityError as error:
                raise AppStoreConflict("A user with that email already exists.") from error
            session.refresh(record)
            return record

    def get_user_by_email(self, email: str) -> UserRecord | None:
        normalized = email.strip().lower()
        with self.session() as session:
            return session.scalar(select(UserRecord).where(UserRecord.email == normalized))

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        with self.session() as session:
            return session.get(UserRecord, user_id)

    def update_user_profile(
        self,
        user_id: str,
        *,
        name: str | None = None,
        role: str | None = None,
        dept: str | None = None,
    ) -> UserRecord | None:
        with self.session() as session:
            record = session.get(UserRecord, user_id)
            if record is None:
                return None
            if name is not None:
                record.name = name
            if role is not None:
                record.role = role
            if dept is not None:
                record.dept = dept
            record.updated_at_utc = _utcnow()
            session.flush()
            session.refresh(record)
            return record

    def list_users(self) -> list[UserRecord]:
        with self.session() as session:
            return list(session.scalars(select(UserRecord).order_by(UserRecord.created_at_utc.desc())))

    def update_user_admin(
        self,
        user_id: str,
        updates: dict[str, Any],
        *,
        updated_by_user_id: str | None = None,
    ) -> UserRecord | None:
        with self.session() as session:
            record = session.get(UserRecord, user_id)
            if record is None:
                return None
            for key, value in updates.items():
                if key in {"acl_tags_json", "app_role", "dept", "name", "password_hash", "role", "status"}:
                    setattr(record, key, value)
            if "status" in updates and updates["status"] == "active" and record.approved_at_utc is None:
                record.approved_at_utc = _utcnow()
                record.approved_by_user_id = updated_by_user_id
            if "approved_at_utc" in updates:
                record.approved_at_utc = updates["approved_at_utc"]
            if "approved_by_user_id" in updates:
                record.approved_by_user_id = updates["approved_by_user_id"]
            record.updated_at_utc = _utcnow()
            record.updated_by_user_id = updated_by_user_id
            session.flush()
            session.refresh(record)
            return record

    def record_last_login(self, user_id: str, when: datetime | None = None) -> UserRecord | None:
        with self.session() as session:
            record = session.get(UserRecord, user_id)
            if record is None:
                return None
            record.last_login_at_utc = when or _utcnow()
            record.updated_at_utc = record.updated_at_utc or record.last_login_at_utc
            session.flush()
            session.refresh(record)
            return record

    def create_session(self, record: SessionRecord) -> SessionRecord:
        with self.session() as session:
            session.add(record)
            session.flush()
            session.refresh(record)
            return record

    def get_active_session(self, session_id: str, now: datetime | None = None) -> tuple[SessionRecord, UserRecord] | None:
        now = now or _utcnow()
        with self.session() as session:
            row = session.execute(
                select(SessionRecord, UserRecord)
                .join(UserRecord, UserRecord.user_id == SessionRecord.user_id)
                .where(SessionRecord.session_id == session_id)
                .where(SessionRecord.revoked_at_utc.is_(None))
                .where(SessionRecord.expires_at_utc > now)
            ).first()
            if row is None:
                return None
            return row[0], row[1]

    def revoke_session(self, session_id: str) -> bool:
        with self.session() as session:
            record = session.get(SessionRecord, session_id)
            if record is None:
                return False
            record.revoked_at_utc = _utcnow()
            return True

    def record_query(self, record: QueryLogRecord) -> None:
        with self.session() as session:
            session.add(record)

    def trending_questions(
        self,
        *,
        tenant_id: str,
        allowed_acl_tags: set[str],
        since: datetime,
        limit: int,
    ) -> list[tuple[str, str | None, int, int, datetime]]:
        with self.session() as session:
            records = list(
                session.scalars(
                    select(QueryLogRecord)
                    .where(QueryLogRecord.tenant_id == tenant_id)
                    .where(QueryLogRecord.created_at_utc >= since)
                    .order_by(QueryLogRecord.created_at_utc.desc())
                    .limit(max(limit * 100, 500))
                )
            )

        groups: dict[tuple[str, str | None], dict[str, object]] = {}
        for record in records:
            acl_tags = set(_json_list(record.acl_tags_json))
            if acl_tags and not acl_tags.intersection(allowed_acl_tags):
                continue
            key = (record.normalized_question, record.topic_id)
            group = groups.setdefault(
                key,
                {
                    "question": record.question,
                    "topic_id": record.topic_id,
                    "user_days": set(),
                    "unique_users": set(),
                    "last_asked_utc": record.created_at_utc,
                },
            )
            last_asked_utc = group["last_asked_utc"]
            if isinstance(last_asked_utc, datetime) and record.created_at_utc > last_asked_utc:
                group["question"] = record.question
                group["last_asked_utc"] = record.created_at_utc
            user_days = group["user_days"]
            unique_users = group["unique_users"]
            if isinstance(user_days, set):
                user_days.add((record.user_id, record.created_at_utc.date().isoformat()))
            if isinstance(unique_users, set):
                unique_users.add(record.user_id)

        ranked = []
        for group in groups.values():
            user_days = group["user_days"]
            unique_users = group["unique_users"]
            last_asked_utc = group["last_asked_utc"]
            if not isinstance(user_days, set) or not isinstance(unique_users, set) or not isinstance(last_asked_utc, datetime):
                continue
            count = len(user_days)
            if count <= 0:
                continue
            ranked.append(
                (
                    str(group["question"]),
                    group["topic_id"] if isinstance(group["topic_id"], str) else None,
                    count,
                    len(unique_users),
                    last_asked_utc,
                )
            )

        ranked.sort(key=lambda item: (-item[2], -item[3], -item[4].timestamp()))
        return ranked[:limit]

    def trending_questions_raw_count(
        self,
        *,
        tenant_id: str,
        allowed_acl_tags: set[str],
        since: datetime,
        limit: int,
    ) -> list[tuple[str, str | None, int]]:
        with self.session() as session:
            rows = session.execute(
                select(
                    QueryLogRecord.normalized_question,
                    QueryLogRecord.topic_id,
                    func.count(QueryLogRecord.id),
                    func.max(QueryLogRecord.question),
                    func.max(QueryLogRecord.acl_tags_json),
                )
                .where(QueryLogRecord.tenant_id == tenant_id)
                .where(QueryLogRecord.created_at_utc >= since)
                .group_by(QueryLogRecord.normalized_question, QueryLogRecord.topic_id)
                .order_by(func.count(QueryLogRecord.id).desc(), func.max(QueryLogRecord.created_at_utc).desc())
                .limit(max(limit * 5, limit))
            ).all()
        filtered: list[tuple[str, str | None, int]] = []
        for _normalized, topic_id, count, question, acl_tags_json in rows:
            acl_tags = set(_json_list(acl_tags_json))
            if acl_tags and not acl_tags.intersection(allowed_acl_tags):
                continue
            filtered.append((str(question), topic_id, int(count)))
            if len(filtered) >= limit:
                break
        return filtered

    def create_feedback(self, record: FeedbackRecord) -> FeedbackRecord:
        with self.session() as session:
            session.add(record)
            session.flush()
            session.refresh(record)
            return record

    def seed_topics_if_empty(self, topics: list[AppTopicRecord]) -> None:
        if not topics:
            return
        with self.session() as session:
            existing_count = session.scalar(select(func.count(AppTopicRecord.topic_id))) or 0
            if existing_count:
                return
            for topic in topics:
                session.add(topic)

    def list_topic_records(self, *, enabled_only: bool = False) -> list[AppTopicRecord]:
        with self.session() as session:
            statement = select(AppTopicRecord).order_by(AppTopicRecord.name.asc())
            if enabled_only:
                statement = statement.where(AppTopicRecord.enabled.is_(True))
            return list(session.scalars(statement))

    def delete_topic_records(self, topic_ids: list[str]) -> int:
        ids = [topic_id for topic_id in dict.fromkeys(topic_ids) if topic_id]
        if not ids:
            return 0
        with self.session() as session:
            result = session.execute(delete(AppTopicRecord).where(AppTopicRecord.topic_id.in_(ids)))
            return int(result.rowcount or 0)

    def get_topic_record(self, topic_id: str, *, enabled_only: bool = False) -> AppTopicRecord | None:
        with self.session() as session:
            record = session.get(AppTopicRecord, topic_id)
            if record is None:
                return None
            if enabled_only and not record.enabled:
                return None
            return record

    def upsert_topic_record(
        self,
        topic_id: str,
        updates: dict[str, Any],
        *,
        updated_by_user_id: str | None = None,
    ) -> AppTopicRecord:
        now = _utcnow()
        with self.session() as session:
            record = session.get(AppTopicRecord, topic_id)
            if record is None:
                record = AppTopicRecord(
                    topic_id=topic_id,
                    name=str(updates.get("name") or topic_id),
                    description=str(updates.get("description") or ""),
                    icon=updates.get("icon"),
                    acl_tags_json=updates.get("acl_tags_json", "[]"),
                    source_filters_json=updates.get("source_filters_json", "[]"),
                    section_filters_json=updates.get("section_filters_json", "[]"),
                    retrieval_tags_json=updates.get("retrieval_tags_json", "[]"),
                    suggested_questions_json=updates.get("suggested_questions_json", "[]"),
                    section_key=updates.get("section_key"),
                    auto_managed=bool(updates.get("auto_managed", False)),
                    enabled=bool(updates.get("enabled", True)),
                    created_at_utc=now,
                    updated_at_utc=now,
                    updated_by_user_id=updated_by_user_id,
                )
                session.add(record)
            else:
                for key, value in updates.items():
                    if key in {
                        "name",
                        "description",
                        "icon",
                        "acl_tags_json",
                        "source_filters_json",
                        "section_filters_json",
                        "retrieval_tags_json",
                        "suggested_questions_json",
                        "section_key",
                        "auto_managed",
                        "enabled",
                    }:
                        setattr(record, key, value)
                record.updated_at_utc = now
                record.updated_by_user_id = updated_by_user_id
            session.flush()
            session.refresh(record)
            return record

    def get_ui_settings(self) -> UiSettingsRecord:
        with self.session() as session:
            record = session.get(UiSettingsRecord, "default")
            if record is None:
                record = UiSettingsRecord(
                    settings_id="default",
                    app_name="Company Knowledge",
                    app_subtitle="Assistant",
                    accent_hue=45,
                    logo_url=None,
                    logo_text=None,
                    updated_at_utc=_utcnow(),
                    updated_by_user_id=None,
                )
                session.add(record)
                session.flush()
                session.refresh(record)
            return record

    def update_ui_settings(
        self,
        updates: dict[str, Any],
        *,
        updated_by_user_id: str | None = None,
    ) -> UiSettingsRecord:
        with self.session() as session:
            record = session.get(UiSettingsRecord, "default")
            if record is None:
                record = UiSettingsRecord(
                    settings_id="default",
                    app_name="Company Knowledge",
                    app_subtitle="Assistant",
                    accent_hue=45,
                    logo_url=None,
                    logo_text=None,
                    updated_at_utc=_utcnow(),
                    updated_by_user_id=None,
                )
                session.add(record)
            for key, value in updates.items():
                if key in {"accent_hue", "app_name", "app_subtitle", "logo_text", "logo_url"}:
                    setattr(record, key, value)
            record.updated_at_utc = _utcnow()
            record.updated_by_user_id = updated_by_user_id
            session.flush()
            session.refresh(record)
            return record

    def list_feedback(self, *, tenant_id: str, user_id: str, limit: int) -> list[FeedbackRecord]:
        with self.session() as session:
            return list(
                session.scalars(
                    select(FeedbackRecord)
                    .where(FeedbackRecord.tenant_id == tenant_id)
                    .where(FeedbackRecord.user_id == user_id)
                    .order_by(FeedbackRecord.created_at_utc.desc())
                    .limit(limit)
                )
            )

    @staticmethod
    def _ensure_sqlite_directory(database_url: str) -> None:
        if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
            return
        path = Path(database_url.removeprefix("sqlite:///"))
        if path.parent and str(path.parent) != ".":
            path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_compat_columns(self) -> None:
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        datetime_type = "TIMESTAMP WITH TIME ZONE" if self.engine.dialect.name == "postgresql" else "DATETIME"
        with self.engine.begin() as connection:
            if "app_users" in table_names:
                existing = {column["name"] for column in inspector.get_columns("app_users")}
                additions = {
                    "status": "ALTER TABLE app_users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'",
                    "app_role": "ALTER TABLE app_users ADD COLUMN app_role VARCHAR(32) NOT NULL DEFAULT 'user'",
                    "approved_by_user_id": "ALTER TABLE app_users ADD COLUMN approved_by_user_id VARCHAR(64)",
                    "approved_at_utc": f"ALTER TABLE app_users ADD COLUMN approved_at_utc {datetime_type}",
                    "last_login_at_utc": f"ALTER TABLE app_users ADD COLUMN last_login_at_utc {datetime_type}",
                    "updated_by_user_id": "ALTER TABLE app_users ADD COLUMN updated_by_user_id VARCHAR(64)",
                }
                added_status = False
                for column_name, ddl in additions.items():
                    if column_name in existing:
                        continue
                    _add_compat_column(connection, ddl)
                    added_status = added_status or column_name == "status"
                if added_status:
                    connection.execute(text("UPDATE app_users SET status = 'active' WHERE status = 'pending'"))

            if "app_topics" in table_names:
                existing = {column["name"] for column in inspector.get_columns("app_topics")}
                false_default = "FALSE" if self.engine.dialect.name == "postgresql" else "0"
                additions = {
                    "section_filters_json": "ALTER TABLE app_topics ADD COLUMN section_filters_json TEXT NOT NULL DEFAULT '[]'",
                    "section_key": "ALTER TABLE app_topics ADD COLUMN section_key VARCHAR(200)",
                    "auto_managed": f"ALTER TABLE app_topics ADD COLUMN auto_managed BOOLEAN NOT NULL DEFAULT {false_default}",
                }
                for column_name, ddl in additions.items():
                    if column_name in existing:
                        continue
                    _add_compat_column(connection, ddl)


def json_dumps(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"))


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _add_compat_column(connection, ddl: str) -> None:
    try:
        connection.execute(text(ddl))
    except OperationalError as error:
        message = str(error).lower()
        if "duplicate column" in message or "already exists" in message:
            return
        raise

