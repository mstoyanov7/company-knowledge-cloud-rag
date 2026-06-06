from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_account_admin_topics"
down_revision = "0001_app_datastore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"))
    op.add_column("app_users", sa.Column("app_role", sa.String(length=32), nullable=False, server_default="user"))
    op.add_column("app_users", sa.Column("approved_by_user_id", sa.String(length=64), nullable=True))
    op.add_column("app_users", sa.Column("approved_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_users", sa.Column("last_login_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_users", sa.Column("updated_by_user_id", sa.String(length=64), nullable=True))
    op.create_index("ix_app_users_status", "app_users", ["status"])
    op.create_index("ix_app_users_app_role", "app_users", ["app_role"])
    op.execute("UPDATE app_users SET status = 'active' WHERE status = 'pending'")

    op.create_table(
        "app_topics",
        sa.Column("topic_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("acl_tags_json", sa.Text(), nullable=False),
        sa.Column("source_filters_json", sa.Text(), nullable=False),
        sa.Column("retrieval_tags_json", sa.Text(), nullable=False),
        sa.Column("suggested_questions_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("topic_id"),
    )
    op.create_index("ix_app_topics_enabled", "app_topics", ["enabled"])

    op.create_table(
        "ui_settings",
        sa.Column("settings_id", sa.String(length=40), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=False),
        sa.Column("app_subtitle", sa.String(length=200), nullable=False),
        sa.Column("accent_hue", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("logo_text", sa.String(length=20), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("settings_id"),
    )


def downgrade() -> None:
    op.drop_table("ui_settings")
    op.drop_index("ix_app_topics_enabled", table_name="app_topics")
    op.drop_table("app_topics")
    op.drop_index("ix_app_users_app_role", table_name="app_users")
    op.drop_index("ix_app_users_status", table_name="app_users")
    op.drop_column("app_users", "updated_by_user_id")
    op.drop_column("app_users", "last_login_at_utc")
    op.drop_column("app_users", "approved_at_utc")
    op.drop_column("app_users", "approved_by_user_id")
    op.drop_column("app_users", "app_role")
    op.drop_column("app_users", "status")
