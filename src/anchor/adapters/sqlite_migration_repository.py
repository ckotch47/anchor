from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from anchor.adapters.sqlite_support import configure_connection, sqlite_write_lock, utc_now_iso
from anchor.config import default_database_path


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MigrationApplicationResult:
    database_path: Path
    applied: int
    current_version: int
    applied_versions: list[int]


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="0001_initial_schema",
        sql="""
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (document_type IN ('note', 'task', 'history'))
);

CREATE TABLE IF NOT EXISTS notes (
    document_id TEXT PRIMARY KEY,
    note_kind TEXT NOT NULL DEFAULT 'note',
    pinned INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    document_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    due_at TEXT,
    completed_at TEXT,
    blocked_reason TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS history_entries (
    document_id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    payload TEXT NOT NULL,
    correlation_id TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chunk_id, model),
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (document_id, tag),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_links (
    from_document_id TEXT NOT NULL,
    to_document_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_document_id, to_document_id, link_type),
    FOREIGN KEY (from_document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (to_document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    scope TEXT NOT NULL DEFAULT 'runtime',
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);

CREATE TABLE IF NOT EXISTS index_states (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    index_type TEXT NOT NULL,
    state TEXT NOT NULL,
    indexed_at TEXT,
    stale_since TEXT,
    last_error TEXT,
    PRIMARY KEY (entity_type, entity_id, index_type)
);

CREATE INDEX IF NOT EXISTS idx_documents_type_updated_at ON documents(document_type, updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source, source_ref);
CREATE INDEX IF NOT EXISTS idx_notes_pinned_archived_at ON notes(pinned, archived_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status_priority_due_at ON tasks(status, priority, due_at);
CREATE INDEX IF NOT EXISTS idx_history_entries_actor ON history_entries(actor);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id_chunk_index ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag);
CREATE INDEX IF NOT EXISTS idx_document_links_from_document_id ON document_links(from_document_id);
CREATE INDEX IF NOT EXISTS idx_document_links_to_document_id ON document_links(to_document_id);
CREATE INDEX IF NOT EXISTS idx_schema_migrations_version ON schema_migrations(version);
CREATE INDEX IF NOT EXISTS idx_index_states_state_type ON index_states(state, index_type);
""".strip(),
    ),
    Migration(
        version=2,
        name="0002_document_chunks_fts",
        sql="""
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    document_type UNINDEXED,
    document_id UNINDEXED,
    chunk_id UNINDEXED,
    title,
    chunk_text
);
""".strip(),
    ),
    Migration(
        version=3,
        name="0003_rebuild_document_chunks_fts_with_document_type",
        sql="""
DROP TABLE IF EXISTS document_chunks_fts;

CREATE VIRTUAL TABLE document_chunks_fts USING fts5(
    document_type UNINDEXED,
    document_id UNINDEXED,
    chunk_id UNINDEXED,
    title,
    chunk_text
);

INSERT INTO document_chunks_fts (document_type, document_id, chunk_id, title, chunk_text)
SELECT
    d.document_type,
    c.document_id,
    c.id,
    d.title,
    c.chunk_text
FROM document_chunks AS c
JOIN documents AS d ON d.id = c.document_id
WHERE d.deleted_at IS NULL;
""".strip(),
    ),
    Migration(
        version=4,
        name="0004_add_project_and_metatags_columns",
        sql="""
ALTER TABLE documents ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE documents ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';
ALTER TABLE notes ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE notes ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';
ALTER TABLE tasks ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE tasks ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';
ALTER TABLE history_entries ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE history_entries ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';
ALTER TABLE document_chunks ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE document_chunks ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';
ALTER TABLE chunk_embeddings ADD COLUMN project TEXT NOT NULL DEFAULT 'workspace';
ALTER TABLE chunk_embeddings ADD COLUMN metatags TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_documents_project_type_updated_at ON documents(project, document_type, updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_project_pinned_archived_at ON notes(project, pinned, archived_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status_priority_due_at ON tasks(project, status, priority, due_at);
CREATE INDEX IF NOT EXISTS idx_history_entries_project_actor ON history_entries(project, actor);
CREATE INDEX IF NOT EXISTS idx_document_chunks_project_document_id_chunk_index ON document_chunks(project, document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_project_model ON chunk_embeddings(project, model);
""".strip(),
    ),
    Migration(
        version=5,
        name="0005_expand_tasks_schema",
        sql="""
ALTER TABLE tasks ADD COLUMN task_kind TEXT NOT NULL DEFAULT 'task';
ALTER TABLE tasks ADD COLUMN started_at TEXT;
ALTER TABLE tasks ADD COLUMN parent_document_id TEXT;
ALTER TABLE tasks ADD COLUMN blocked_by_document_id TEXT;

CREATE INDEX IF NOT EXISTS idx_tasks_project_task_kind_status_priority_due_at ON tasks(project, task_kind, status, priority, due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project_parent_document_id ON tasks(project, parent_document_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_blocked_by_document_id ON tasks(project, blocked_by_document_id);
""".strip(),
    ),
    Migration(
        version=6,
        name="0006_filesystem_indexing",
        sql="""
PRAGMA foreign_keys = OFF;

CREATE TABLE documents_new (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL DEFAULT 'workspace',
    metatags TEXT NOT NULL DEFAULT '{}',
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (document_type IN ('note', 'task', 'history', 'file'))
);

INSERT INTO documents_new (
    id, project, metatags, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
)
SELECT
    id, project, metatags, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
FROM documents;

DROP TABLE documents;

ALTER TABLE documents_new RENAME TO documents;

PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_documents_type_updated_at ON documents(document_type, updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source, source_ref);
CREATE INDEX IF NOT EXISTS idx_documents_project_type_updated_at ON documents(project, document_type, updated_at);

CREATE TABLE IF NOT EXISTS indexed_files (
    document_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    path TEXT NOT NULL,
    root_path TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    metatags TEXT NOT NULL DEFAULT '{}',
    file_size INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    project TEXT NOT NULL,
    path TEXT NOT NULL,
    root_path TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    chunk_index INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS file_chunks_fts USING fts5(
    document_type UNINDEXED,
    document_id UNINDEXED,
    chunk_id UNINDEXED,
    path,
    chunk_text
);

CREATE INDEX IF NOT EXISTS idx_indexed_files_project_path ON indexed_files(project, path);
CREATE INDEX IF NOT EXISTS idx_indexed_files_project_root_path ON indexed_files(project, root_path);
CREATE INDEX IF NOT EXISTS idx_file_chunks_project_document_id ON file_chunks(project, document_id);
CREATE INDEX IF NOT EXISTS idx_file_chunks_project_path_chunk_index ON file_chunks(project, path, chunk_index);
""".strip(),
    ),
]


class SqliteMigrationRepository:
    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or default_database_path()

    def apply_pending(self) -> MigrationApplicationResult:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite_write_lock(self._database_path):
            connection = sqlite3.connect(self._database_path)
            try:
                self._configure(connection)
                self._ensure_migrations_table(connection)
                applied_versions = self._applied_versions(connection)
                applied = 0
                for migration in MIGRATIONS:
                    if migration.version in applied_versions:
                        continue
                    connection.executescript(migration.sql)
                    self._record_migration(connection, migration)
                    applied += 1
                    applied_versions.append(migration.version)
                connection.commit()
                return MigrationApplicationResult(
                    database_path=self._database_path,
                    applied=applied,
                    current_version=max(applied_versions, default=0),
                    applied_versions=sorted(applied_versions),
                )
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _configure(self, connection: sqlite3.Connection) -> None:
        configure_connection(connection, busy_timeout_ms=250)

    def _ensure_migrations_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )

    def _applied_versions(self, connection: sqlite3.Connection) -> list[int]:
        rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [int(row[0]) for row in rows]

    def _record_migration(self, connection: sqlite3.Connection, migration: Migration) -> None:
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, checksum, applied_at, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                migration.version,
                migration.name,
                migration.checksum,
                utc_now_iso(),
                "applied",
            ),
        )
