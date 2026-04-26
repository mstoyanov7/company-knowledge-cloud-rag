from __future__ import annotations

import json
from datetime import UTC, datetime

import psycopg
from shared_schemas import AppSettings, ChunkDocument, OneNoteCheckpoint, SharePointCheckpoint, SourceDocument


class PostgresMetadataStore:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def ensure_schema(self) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(hashtext('cloud_rag_metadata_schema'))")
                try:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sharepoint_checkpoints (
                            scope_key TEXT PRIMARY KEY,
                            sync_mode TEXT NOT NULL,
                            site_id TEXT,
                            drive_id TEXT,
                            cursor_url TEXT,
                            delta_link TEXT,
                            page_count INTEGER NOT NULL DEFAULT 0,
                            item_count INTEGER NOT NULL DEFAULT 0,
                            updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS onenote_checkpoints (
                            scope_key TEXT PRIMARY KEY,
                            sync_mode TEXT NOT NULL,
                            site_id TEXT,
                            notebook_scope TEXT,
                            last_modified_cursor_utc TIMESTAMPTZ,
                            page_count INTEGER NOT NULL DEFAULT 0,
                            item_count INTEGER NOT NULL DEFAULT 0,
                            updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS source_documents (
                            source_item_id TEXT PRIMARY KEY,
                            tenant_id TEXT NOT NULL,
                            scope_key TEXT NOT NULL,
                            source_system TEXT NOT NULL,
                            source_container TEXT NOT NULL,
                            source_url TEXT NOT NULL,
                            title TEXT NOT NULL,
                            file_name TEXT NOT NULL,
                            file_extension TEXT NOT NULL,
                            mime_type TEXT,
                            section_path TEXT,
                            last_modified_utc TIMESTAMPTZ NOT NULL,
                            acl_tags_json TEXT NOT NULL,
                            content_hash TEXT NOT NULL,
                            content_text TEXT NOT NULL,
                            language TEXT NOT NULL,
                            tags_json TEXT NOT NULL,
                            metadata_json TEXT NOT NULL,
                            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                            updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            deleted_at_utc TIMESTAMPTZ
                        );

                        CREATE TABLE IF NOT EXISTS chunk_documents (
                            chunk_id TEXT PRIMARY KEY,
                            source_item_id TEXT NOT NULL REFERENCES source_documents(source_item_id) ON DELETE CASCADE,
                            tenant_id TEXT NOT NULL,
                            scope_key TEXT NOT NULL,
                            source_system TEXT NOT NULL,
                            source_container TEXT NOT NULL,
                            source_url TEXT NOT NULL,
                            title TEXT NOT NULL,
                            section_path TEXT,
                            last_modified_utc TIMESTAMPTZ NOT NULL,
                            acl_tags_json TEXT NOT NULL,
                            content_hash TEXT NOT NULL,
                            chunk_index INTEGER NOT NULL,
                            chunk_text TEXT NOT NULL,
                            embedding_model TEXT NOT NULL,
                            language TEXT NOT NULL,
                            tags_json TEXT NOT NULL,
                            metadata_json TEXT NOT NULL,
                            updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_source_documents_scope_key ON source_documents(scope_key);
                        CREATE INDEX IF NOT EXISTS idx_chunk_documents_source_item_id ON chunk_documents(source_item_id);
                        """
                    )
                finally:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext('cloud_rag_metadata_schema'))")
            connection.commit()

    def get_checkpoint(self, scope_key: str) -> SharePointCheckpoint | None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT scope_key, sync_mode, site_id, drive_id, cursor_url, delta_link, page_count, item_count, updated_at_utc
                    FROM sharepoint_checkpoints
                    WHERE scope_key = %s
                    """,
                    (scope_key,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return SharePointCheckpoint(
            scope_key=row[0],
            sync_mode=row[1],
            site_id=row[2],
            drive_id=row[3],
            cursor_url=row[4],
            delta_link=row[5],
            page_count=row[6],
            item_count=row[7],
            updated_at_utc=row[8],
        )

    def upsert_checkpoint(self, checkpoint: SharePointCheckpoint) -> SharePointCheckpoint:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sharepoint_checkpoints (
                        scope_key, sync_mode, site_id, drive_id, cursor_url, delta_link, page_count, item_count, updated_at_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scope_key) DO UPDATE SET
                        sync_mode = EXCLUDED.sync_mode,
                        site_id = EXCLUDED.site_id,
                        drive_id = EXCLUDED.drive_id,
                        cursor_url = EXCLUDED.cursor_url,
                        delta_link = EXCLUDED.delta_link,
                        page_count = EXCLUDED.page_count,
                        item_count = EXCLUDED.item_count,
                        updated_at_utc = EXCLUDED.updated_at_utc
                    """,
                    (
                        checkpoint.scope_key,
                        checkpoint.sync_mode,
                        checkpoint.site_id,
                        checkpoint.drive_id,
                        checkpoint.cursor_url,
                        checkpoint.delta_link,
                        checkpoint.page_count,
                        checkpoint.item_count,
                        checkpoint.updated_at_utc,
                    ),
                )
            connection.commit()
        return checkpoint

    def get_onenote_checkpoint(self, scope_key: str) -> OneNoteCheckpoint | None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT scope_key, sync_mode, site_id, notebook_scope, last_modified_cursor_utc, page_count, item_count, updated_at_utc
                    FROM onenote_checkpoints
                    WHERE scope_key = %s
                    """,
                    (scope_key,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return OneNoteCheckpoint(
            scope_key=row[0],
            sync_mode=row[1],
            site_id=row[2],
            notebook_scope=row[3],
            last_modified_cursor_utc=row[4],
            page_count=row[5],
            item_count=row[6],
            updated_at_utc=row[7],
        )

    def upsert_onenote_checkpoint(self, checkpoint: OneNoteCheckpoint) -> OneNoteCheckpoint:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO onenote_checkpoints (
                        scope_key, sync_mode, site_id, notebook_scope, last_modified_cursor_utc, page_count, item_count, updated_at_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scope_key) DO UPDATE SET
                        sync_mode = EXCLUDED.sync_mode,
                        site_id = EXCLUDED.site_id,
                        notebook_scope = EXCLUDED.notebook_scope,
                        last_modified_cursor_utc = EXCLUDED.last_modified_cursor_utc,
                        page_count = EXCLUDED.page_count,
                        item_count = EXCLUDED.item_count,
                        updated_at_utc = EXCLUDED.updated_at_utc
                    """,
                    (
                        checkpoint.scope_key,
                        checkpoint.sync_mode,
                        checkpoint.site_id,
                        checkpoint.notebook_scope,
                        checkpoint.last_modified_cursor_utc,
                        checkpoint.page_count,
                        checkpoint.item_count,
                        checkpoint.updated_at_utc,
                    ),
                )
            connection.commit()
        return checkpoint

    def get_source_document(self, source_item_id: str) -> SourceDocument | None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tenant_id, source_system, source_container, source_item_id, source_url, title, file_name, file_extension,
                           mime_type, section_path, last_modified_utc, acl_tags_json, content_hash, content_text,
                           language, tags_json, metadata_json
                    FROM source_documents
                    WHERE source_item_id = %s AND is_deleted = FALSE
                    """,
                    (source_item_id,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return SourceDocument(
            tenant_id=row[0],
            source_system=row[1],
            source_container=row[2],
            source_item_id=row[3],
            source_url=row[4],
            title=row[5],
            file_name=row[6],
            file_extension=row[7],
            mime_type=row[8],
            section_path=row[9],
            last_modified_utc=row[10],
            acl_tags=json.loads(row[11]),
            content_hash=row[12],
            content_text=row[13],
            language=row[14],
            tags=json.loads(row[15]),
            metadata=json.loads(row[16]),
        )

    def upsert_source_document(self, scope_key: str, document: SourceDocument) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_documents (
                        source_item_id, scope_key, source_system, source_container, source_url, title, file_name,
                        tenant_id, file_extension, mime_type, section_path, last_modified_utc, acl_tags_json, content_hash,
                        content_text, language, tags_json, metadata_json, is_deleted, deleted_at_utc, updated_at_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NULL, %s)
                    ON CONFLICT (source_item_id) DO UPDATE SET
                        scope_key = EXCLUDED.scope_key,
                        source_system = EXCLUDED.source_system,
                        source_container = EXCLUDED.source_container,
                        source_url = EXCLUDED.source_url,
                        title = EXCLUDED.title,
                        file_name = EXCLUDED.file_name,
                        tenant_id = EXCLUDED.tenant_id,
                        file_extension = EXCLUDED.file_extension,
                        mime_type = EXCLUDED.mime_type,
                        section_path = EXCLUDED.section_path,
                        last_modified_utc = EXCLUDED.last_modified_utc,
                        acl_tags_json = EXCLUDED.acl_tags_json,
                        content_hash = EXCLUDED.content_hash,
                        content_text = EXCLUDED.content_text,
                        language = EXCLUDED.language,
                        tags_json = EXCLUDED.tags_json,
                        metadata_json = EXCLUDED.metadata_json,
                        is_deleted = FALSE,
                        deleted_at_utc = NULL,
                        updated_at_utc = EXCLUDED.updated_at_utc
                    """,
                    (
                        document.source_item_id,
                        scope_key,
                        document.source_system,
                        document.source_container,
                        document.source_url,
                        document.title,
                        document.file_name,
                        document.tenant_id,
                        document.file_extension,
                        document.mime_type,
                        document.section_path,
                        document.last_modified_utc,
                        json.dumps(document.acl_tags),
                        document.content_hash,
                        document.content_text,
                        document.language,
                        json.dumps(document.tags),
                        json.dumps(document.metadata),
                        datetime.now(UTC),
                    ),
                )
            connection.commit()

    def mark_source_deleted(self, scope_key: str, source_item_id: str, deleted_at_utc: datetime | None = None) -> None:
        deleted_at = deleted_at_utc or datetime.now(UTC)
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE source_documents
                    SET is_deleted = TRUE, deleted_at_utc = %s, updated_at_utc = %s
                    WHERE source_item_id = %s
                    """,
                    (deleted_at, deleted_at, source_item_id),
                )
                cursor.execute(
                    """
                    DELETE FROM chunk_documents
                    WHERE source_item_id = %s
                    """,
                    (source_item_id,),
                )
            connection.commit()

    def replace_chunks(self, scope_key: str, source_item_id: str, chunks: list[ChunkDocument]) -> None:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM chunk_documents WHERE source_item_id = %s", (source_item_id,))
                for chunk in chunks:
                    cursor.execute(
                        """
                        INSERT INTO chunk_documents (
                            chunk_id, source_item_id, scope_key, source_system, source_container, source_url, title,
                            tenant_id,
                            section_path, last_modified_utc, acl_tags_json, content_hash, chunk_index, chunk_text,
                            embedding_model, language, tags_json, metadata_json, updated_at_utc
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chunk.chunk_id,
                            chunk.source_item_id,
                            scope_key,
                            chunk.source_system,
                            chunk.source_container,
                            chunk.source_url,
                            chunk.title,
                            chunk.tenant_id,
                            chunk.section_path,
                            chunk.last_modified_utc,
                            json.dumps(chunk.acl_tags),
                            chunk.content_hash,
                            chunk.chunk_index,
                            chunk.chunk_text,
                            chunk.embedding_model,
                            chunk.language,
                            json.dumps(chunk.tags),
                            json.dumps(chunk.metadata),
                            datetime.now(UTC),
                        ),
                    )
            connection.commit()

    def list_active_source_documents(self, scope_key: str, source_system: str) -> list[SourceDocument]:
        with psycopg.connect(self.settings.postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tenant_id, source_system, source_container, source_item_id, source_url, title, file_name, file_extension,
                           mime_type, section_path, last_modified_utc, acl_tags_json, content_hash, content_text,
                           language, tags_json, metadata_json
                    FROM source_documents
                    WHERE scope_key = %s AND source_system = %s AND is_deleted = FALSE
                    ORDER BY source_item_id ASC
                    """,
                    (scope_key, source_system),
                )
                rows = cursor.fetchall()
        documents: list[SourceDocument] = []
        for row in rows:
            documents.append(
                SourceDocument(
                    tenant_id=row[0],
                    source_system=row[1],
                    source_container=row[2],
                    source_item_id=row[3],
                    source_url=row[4],
                    title=row[5],
                    file_name=row[6],
                    file_extension=row[7],
                    mime_type=row[8],
                    section_path=row[9],
                    last_modified_utc=row[10],
                    acl_tags=json.loads(row[11]),
                    content_hash=row[12],
                    content_text=row[13],
                    language=row[14],
                    tags=json.loads(row[15]),
                    metadata=json.loads(row[16]),
                )
            )
        return documents
