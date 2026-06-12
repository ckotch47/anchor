from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_chunks (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_embeddings (
    item_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, chunk_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES item_chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (item_id, tag),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_links (
    from_item_id TEXT NOT NULL,
    to_item_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_item_id, to_item_id, link_type),
    FOREIGN KEY (from_item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (to_item_id) REFERENCES items(id) ON DELETE CASCADE
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
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_items_type_status_created_at ON items(type, status, created_at);
CREATE INDEX IF NOT EXISTS idx_item_links_from_item_id ON item_links(from_item_id);
CREATE INDEX IF NOT EXISTS idx_item_links_to_item_id ON item_links(to_item_id);
CREATE INDEX IF NOT EXISTS idx_schema_migrations_version ON schema_migrations(version);
CREATE INDEX IF NOT EXISTS idx_index_states_state_type ON index_states(state, index_type);
""".strip(),
    ),
]


class SqliteMigrationRepository:
    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or default_database_path()

    def apply_pending(self) -> MigrationApplicationResult:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
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
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 250")

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
                datetime.now(timezone.utc).isoformat(),
                "applied",
            ),
        )
