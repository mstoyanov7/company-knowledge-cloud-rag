from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_app_datastore"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("acl_tags_json", sa.Text(), nullable=False),
        sa.Column("groups_json", sa.Text(), nullable=False),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("dept", sa.String(length=120), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_app_users_email", "app_users", ["email"], unique=True)
    op.create_index("ix_app_users_tenant_id", "app_users", ["tenant_id"])

    op.create_table(
        "app_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_app_sessions_user_id", "app_sessions", ["user_id"])
    op.create_index("ix_app_sessions_expires_at_utc", "app_sessions", ["expires_at_utc"])

    op.create_table(
        "query_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("topic_id", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.String(length=120), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("acl_tags_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_log_normalized_question", "query_log", ["normalized_question"])
    op.create_index("ix_query_log_question_hash", "query_log", ["question_hash"])
    op.create_index("ix_query_log_topic_id", "query_log", ["topic_id"])
    op.create_index("ix_query_log_tenant_id", "query_log", ["tenant_id"])
    op.create_index("ix_query_log_user_id", "query_log", ["user_id"])
    op.create_index("ix_query_log_created_at_utc", "query_log", ["created_at_utc"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("response_id", sa.String(length=120), nullable=False),
        sa.Column("conversation_id", sa.String(length=120), nullable=True),
        sa.Column("rating", sa.String(length=20), nullable=True),
        sa.Column("flag_gap", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("topic_id", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.String(length=120), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("acl_tags_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_response_id", "feedback", ["response_id"])
    op.create_index("ix_feedback_conversation_id", "feedback", ["conversation_id"])
    op.create_index("ix_feedback_topic_id", "feedback", ["topic_id"])
    op.create_index("ix_feedback_tenant_id", "feedback", ["tenant_id"])
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_created_at_utc", "feedback", ["created_at_utc"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("query_log")
    op.drop_table("app_sessions")
    op.drop_table("app_users")

