"""Seed the "trending questions" list with chosen questions (demo data).

Trending ranks a question by how many DISTINCT (user, day) pairs asked it in the
last ~30 days (asking 100x as one user still counts as 1). This script inserts
synthetic query-log rows through the app's own store, so the schema and timestamp
format are always correct.

Usage (from the repo root):
    python scripts/seed_trending.py

Edit QUESTIONS below: each is (question text as it should appear, count). The
count is how many distinct synthetic users "asked" it, i.e. the trending number.
Question text is shown verbatim, so keep the natural (mixed-case) wording to look
like real user input.

With RESET_FIRST = True the whole query log is cleared first, so running the
script sets trending to EXACTLY these questions. No restart needed; reload the
Home page to see the updated list.
"""
from __future__ import annotations

from sqlalchemy import delete

from shared_schemas import AppSettings, UserContext
from rag_api.persistence.app_store import AppDataStore, QueryLogRecord
from rag_api.services.activity import QueryLogService

DB_URL = "sqlite:///./.cache/rag_api.sqlite3"
TENANT_ID = "local-tenant"
RESET_FIRST = True  # clear existing query log so trending == exactly QUESTIONS

# (question text shown verbatim, count == distinct users, topic_id).
# The Home view only shows a trending question if its topic_id is one of the
# topics the viewer can see, so each question must be attached to a real topic.
QUESTIONS: list[tuple[str, int, str]] = [
    ("How to setup flutter-elinux?", 12, "section-project-setups"),
    ("what is the working time", 8, "section-people-and-hr"),
    ("who is leading HMI team?", 3, "section-engineering-handbook"),
]


def main() -> None:
    settings = AppSettings(app_env="local", app_database_url=DB_URL)
    store = AppDataStore(settings)
    store.ensure_schema()

    if RESET_FIRST:
        with store.session() as session:
            session.execute(delete(QueryLogRecord))
            session.commit()
        print("Cleared existing query log.")

    service = QueryLogService(store=store)
    total = 0
    for question, count, topic_id in QUESTIONS:
        for index in range(max(1, int(count))):
            service.record_question(
                question=question,
                topic_id=topic_id,
                user_context=UserContext(
                    user_id=f"seed-user-{index + 1}",
                    tenant_id=TENANT_ID,
                    acl_tags=[],
                ),
            )
            total += 1

    print(f"Seeded {len(QUESTIONS)} trending questions ({total} rows).")


if __name__ == "__main__":
    main()
