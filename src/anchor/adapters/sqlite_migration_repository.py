from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from anchor.adapters.sqlite_support import configure_connection, connect_trusted_sqlite, sqlite_write_lock, utc_now_iso
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
CREATE INDEX IF NOT EXISTS idx_indexed_files_project_root_path_path ON indexed_files(project, root_path, path);
CREATE INDEX IF NOT EXISTS idx_file_chunks_project_document_id ON file_chunks(project, document_id);
CREATE INDEX IF NOT EXISTS idx_file_chunks_project_path_chunk_index ON file_chunks(project, path, chunk_index);
""".strip(),
    ),
    Migration(
        version=7,
        name="0007_add_documents_correlation_id",
        sql="""
ALTER TABLE documents ADD COLUMN correlation_id TEXT NOT NULL DEFAULT '';
""".strip(),
    ),
    Migration(
        version=8,
        name="0008_memory_facts",
        sql="""
CREATE TABLE IF NOT EXISTS memory_facts (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('chat', 'project', 'global')),
    project TEXT,
    source_chat_id TEXT,
    fact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'active', 'superseded', 'conflicted', 'deleted')),
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    valid_from TEXT,
    valid_until TEXT,
    supersedes_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (supersedes_id) REFERENCES memory_facts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_facts_scope ON memory_facts(scope);
CREATE INDEX IF NOT EXISTS idx_memory_facts_project ON memory_facts(project);
CREATE INDEX IF NOT EXISTS idx_memory_facts_source_chat_id ON memory_facts(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_memory_facts_status ON memory_facts(status);
CREATE INDEX IF NOT EXISTS idx_memory_facts_fact_type ON memory_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_memory_facts_supersedes_id ON memory_facts(supersedes_id);
CREATE INDEX IF NOT EXISTS idx_memory_facts_status_updated_at_id
    ON memory_facts(status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_memory_facts_project_status_updated_at_id
    ON memory_facts(project, status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_memory_facts_source_chat_status_updated_at_id
    ON memory_facts(source_chat_id, status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_memory_facts_type_status_updated_at_id
    ON memory_facts(fact_type, status, updated_at DESC, id DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
    fact_id UNINDEXED,
    content
);
""".strip(),
    ),
    Migration(
        version=9,
        name="0009_memory_pipeline_and_scenarios",
        sql="""
CREATE TABLE IF NOT EXISTS memory_pipeline_checkpoints (
    pipeline_key TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    chat_id TEXT,
    last_history_updated_at TEXT,
    last_run_at TEXT,
    processed_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('idle', 'running', 'completed', 'error')),
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_scenarios (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('project', 'global')),
    project TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    fact_ids TEXT NOT NULL DEFAULT '[]',
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_pipeline_project_chat ON memory_pipeline_checkpoints(project, chat_id);
CREATE INDEX IF NOT EXISTS idx_memory_pipeline_status ON memory_pipeline_checkpoints(status);
CREATE INDEX IF NOT EXISTS idx_memory_scenarios_scope_project_status ON memory_scenarios(scope, project, status);
CREATE INDEX IF NOT EXISTS idx_memory_scenarios_updated_at_id ON memory_scenarios(updated_at DESC, id DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_scenarios_fts USING fts5(
    scenario_id UNINDEXED,
    title,
    summary
);
""".strip(),
    ),
    Migration(
        version=10,
        name="0010_memory_extraction_batch_state",
        sql="""
ALTER TABLE memory_pipeline_checkpoints ADD COLUMN pending_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memory_pipeline_checkpoints ADD COLUMN pending_since REAL;
ALTER TABLE memory_pipeline_checkpoints ADD COLUMN last_extraction_at REAL;
        """.strip(),
    ),
    Migration(
        version=11,
        name="0011_allow_file_chunk_embeddings",
        sql="""
PRAGMA foreign_keys=OFF;
DROP INDEX IF EXISTS idx_chunk_embeddings_model;
DROP INDEX IF EXISTS idx_chunk_embeddings_project_model;
ALTER TABLE chunk_embeddings RENAME TO chunk_embeddings_legacy;
CREATE TABLE chunk_embeddings (
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT 'workspace',
    metatags TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (chunk_id, model)
);
INSERT INTO chunk_embeddings (chunk_id, model, embedding, created_at, project, metatags)
SELECT chunk_id, model, embedding, created_at, project, metatags
FROM chunk_embeddings_legacy;
DROP TABLE chunk_embeddings_legacy;
CREATE INDEX idx_chunk_embeddings_model ON chunk_embeddings(model);
CREATE INDEX idx_chunk_embeddings_project_model ON chunk_embeddings(project, model);
PRAGMA foreign_keys=ON;
""".strip(),
    ),
    Migration(
        version=12,
        name="0012_task_external_keys",
        sql="""
ALTER TABLE tasks ADD COLUMN external_key TEXT;

CREATE TABLE IF NOT EXISTS task_external_key_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    external_key TEXT NOT NULL,
    document_ids TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

INSERT INTO task_external_key_quarantine(
    project, external_key, document_ids, reason, detected_at
)
SELECT d.project, d.source_ref, json_group_array(d.id),
       'duplicate_legacy_myskills_identity', CURRENT_TIMESTAMP
FROM documents AS d
JOIN tasks AS t ON t.document_id = d.id AND t.project = d.project
WHERE d.source = 'myskills-orchestration' AND d.source_ref <> ''
GROUP BY d.project, d.source_ref
HAVING COUNT(*) > 1;

UPDATE tasks
SET external_key = (
    SELECT d.source_ref FROM documents AS d
    WHERE d.id = tasks.document_id AND d.project = tasks.project
      AND d.source = 'myskills-orchestration' AND d.source_ref <> ''
)
WHERE EXISTS (
    SELECT 1 FROM documents AS d
    WHERE d.id = tasks.document_id AND d.project = tasks.project
      AND d.source = 'myskills-orchestration' AND d.source_ref <> ''
      AND 1 = (
          SELECT COUNT(*)
          FROM documents AS duplicate
          JOIN tasks AS duplicate_task
            ON duplicate_task.document_id = duplicate.id
           AND duplicate_task.project = duplicate.project
          WHERE duplicate.project = d.project
            AND duplicate.source = 'myskills-orchestration'
            AND duplicate.source_ref = d.source_ref
      )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_project_external_key
    ON tasks(project, external_key)
    WHERE external_key IS NOT NULL AND external_key <> '';
CREATE INDEX IF NOT EXISTS idx_task_external_key_quarantine_project
    ON task_external_key_quarantine(project, external_key);
""".strip(),
    ),
    Migration(
        version=13,
        name="0013_quarantine_cross_project_links",
        sql="""
CREATE TABLE IF NOT EXISTS document_link_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_document_id TEXT NOT NULL,
    to_document_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_relation_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_document_id TEXT NOT NULL,
    task_project TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    related_document_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

INSERT INTO document_link_quarantine(
    from_document_id, to_document_id, link_type, reason, detected_at
)
SELECT link.from_document_id, link.to_document_id, link.link_type,
       'cross_project_or_deleted_endpoint', CURRENT_TIMESTAMP
FROM document_links AS link
LEFT JOIN documents AS source ON source.id = link.from_document_id
LEFT JOIN documents AS target ON target.id = link.to_document_id
WHERE source.id IS NULL OR target.id IS NULL
   OR source.deleted_at IS NOT NULL OR target.deleted_at IS NOT NULL
   OR source.project <> target.project;

DELETE FROM document_links
WHERE EXISTS (
    SELECT 1 FROM document_link_quarantine AS quarantine
    WHERE quarantine.from_document_id = document_links.from_document_id
      AND quarantine.to_document_id = document_links.to_document_id
      AND quarantine.link_type = document_links.link_type
);

INSERT INTO task_relation_quarantine(
    task_document_id, task_project, relation_type, related_document_id,
    reason, detected_at
)
SELECT t.document_id, t.project, 'parent', t.parent_document_id,
       'cross_project_or_deleted_endpoint', CURRENT_TIMESTAMP
FROM tasks AS t
LEFT JOIN documents AS related ON related.id = t.parent_document_id
LEFT JOIN tasks AS related_task
  ON related_task.document_id = related.id AND related_task.project = related.project
WHERE t.parent_document_id IS NOT NULL
  AND (
      related.id IS NULL OR related.deleted_at IS NOT NULL
      OR related.project <> t.project OR related.document_type <> 'task'
      OR related_task.document_id IS NULL
  )
UNION ALL
SELECT t.document_id, t.project, 'blocked_by', t.blocked_by_document_id,
       'cross_project_or_deleted_endpoint', CURRENT_TIMESTAMP
FROM tasks AS t
LEFT JOIN documents AS related ON related.id = t.blocked_by_document_id
LEFT JOIN tasks AS related_task
  ON related_task.document_id = related.id AND related_task.project = related.project
WHERE t.blocked_by_document_id IS NOT NULL
  AND (
      related.id IS NULL OR related.deleted_at IS NOT NULL
      OR related.project <> t.project OR related.document_type <> 'task'
      OR related_task.document_id IS NULL
  );

UPDATE tasks
SET parent_document_id = NULL
WHERE EXISTS (
    SELECT 1 FROM task_relation_quarantine AS quarantine
    WHERE quarantine.task_document_id = tasks.document_id
      AND quarantine.task_project = tasks.project
      AND quarantine.relation_type = 'parent'
      AND quarantine.related_document_id = tasks.parent_document_id
);

UPDATE tasks
SET blocked_by_document_id = NULL
WHERE EXISTS (
    SELECT 1 FROM task_relation_quarantine AS quarantine
    WHERE quarantine.task_document_id = tasks.document_id
      AND quarantine.task_project = tasks.project
      AND quarantine.relation_type = 'blocked_by'
      AND quarantine.related_document_id = tasks.blocked_by_document_id
);

CREATE INDEX IF NOT EXISTS idx_task_relation_quarantine_project
    ON task_relation_quarantine(task_project, task_document_id);
""".strip(),
    ),
]


class SqliteMigrationRepository:
    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or default_database_path()

    def apply_pending(self) -> MigrationApplicationResult:
        self._database_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with sqlite_write_lock(self._database_path):
            connection = connect_trusted_sqlite(self._database_path)
            try:
                self._configure(connection)
                self._ensure_migrations_table(connection)
                applied_versions = self._applied_versions(connection)
                applied = 0
                for migration in MIGRATIONS:
                    if migration.version in applied_versions:
                        continue
                    self._apply_migration(connection, migration)
                    applied += 1
                    applied_versions.append(migration.version)
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

    def _apply_migration(
        self, connection: sqlite3.Connection, migration: Migration
    ) -> None:
        statements = self._migration_statements(migration.sql)
        manages_foreign_keys = any(
            statement.strip().lower() == "pragma foreign_keys=off;"
            for statement in statements
        )
        if manages_foreign_keys:
            connection.execute("PRAGMA foreign_keys=OFF")
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in statements:
                normalized = statement.strip().lower()
                if normalized in {
                    "pragma foreign_keys=off;",
                    "pragma foreign_keys=on;",
                }:
                    continue
                connection.execute(statement)
            self._record_migration(connection, migration)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if manages_foreign_keys:
                connection.execute("PRAGMA foreign_keys=ON")

    @staticmethod
    def _migration_statements(sql: str) -> list[str]:
        statements: list[str] = []
        buffer = ""
        for character in sql:
            buffer += character
            if character == ";" and sqlite3.complete_statement(buffer):
                if buffer.strip():
                    statements.append(buffer.strip())
                buffer = ""
        if buffer.strip():
            raise ValueError("migration SQL must end with a complete statement")
        return statements

    def _configure(self, connection: sqlite3.Connection) -> None:
        configure_connection(connection, busy_timeout_ms=250, database_path=self._database_path)

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
