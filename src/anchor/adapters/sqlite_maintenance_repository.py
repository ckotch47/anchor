from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import configure_connection, sqlite_write_lock, utc_now_iso


class SqliteMaintenanceRepository(SqliteRepositoryBase):
    MAINTENANCE_SCOPE = "maintenance"
    LAST_VACUUM_KEY = "last_vacuum"
    AUTO_MAINTENANCE_DAYS = 7

    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

    def checkpoint_wal(self) -> dict[str, int]:
        with self._write_connect() as connection:
            row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            connection.commit()
        return self._wal_checkpoint_stats(row)

    def auto_maintain_if_due(self, *, interval_days: int = AUTO_MAINTENANCE_DAYS) -> bool:
        if interval_days <= 0:
            raise ValueError("interval_days must be greater than zero")
        with sqlite_write_lock(self._database_path):
            connection = sqlite3.connect(self._database_path)
            try:
                configure_connection(connection, busy_timeout_ms=250)
                last_vacuum = self._get_setting(connection, self.MAINTENANCE_SCOPE, self.LAST_VACUUM_KEY)
                if not self._maintenance_due(last_vacuum, interval_days=interval_days):
                    return False
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._rebuild_search_indexes(connection)
                connection.commit()
                connection.close()

                vacuum_connection = sqlite3.connect(self._database_path)
                try:
                    configure_connection(vacuum_connection, busy_timeout_ms=250)
                    vacuum_connection.execute("VACUUM")
                    vacuum_connection.commit()
                finally:
                    vacuum_connection.close()

                settings_connection = sqlite3.connect(self._database_path)
                try:
                    configure_connection(settings_connection, busy_timeout_ms=250)
                    self._set_setting(
                        settings_connection,
                        self.MAINTENANCE_SCOPE,
                        self.LAST_VACUUM_KEY,
                        utc_now_iso(),
                    )
                    settings_connection.commit()
                finally:
                    settings_connection.close()
                return True
            finally:
                try:
                    connection.close()
                except Exception:
                    pass

    def purge_deleted_documents(self, *, project: str | None = None, deleted_before: str | None = None) -> int:
        clauses = ["deleted_at IS NOT NULL"]
        params: list[object] = []
        if project is not None:
            clauses.append("project = ?")
            params.append(project)
        if deleted_before is not None:
            clauses.append("deleted_at <= ?")
            params.append(deleted_before)
        query = f"DELETE FROM documents WHERE {' AND '.join(clauses)}"
        with self._write_connect() as connection:
            result = connection.execute(query, params)
            connection.commit()
            return int(result.rowcount)

    def rebuild_search_indexes(self) -> list[str]:
        with self._write_connect() as connection:
            rebuilt = self._rebuild_search_indexes(connection)
            connection.commit()
        return rebuilt

    def vacuum(self) -> None:
        with sqlite_write_lock(self._database_path):
            connection = sqlite3.connect(self._database_path)
            try:
                configure_connection(connection, busy_timeout_ms=250)
                connection.execute("VACUUM")
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _wal_checkpoint_stats(row: sqlite3.Row | tuple[int, int, int] | None) -> dict[str, int]:
        if row is None:
            return {"busy": 0, "log": 0, "checkpointed": 0}
        return {
            "busy": int(row[0]),
            "log": int(row[1]),
            "checkpointed": int(row[2]),
        }

    @staticmethod
    def _get_setting(connection: sqlite3.Connection, scope: str, key: str) -> str | None:
        row = connection.execute(
            """
            SELECT value
            FROM settings
            WHERE scope = ? AND key = ?
            """,
            (scope, key),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    @staticmethod
    def _set_setting(connection: sqlite3.Connection, scope: str, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO settings (scope, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scope, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (scope, key, value, utc_now_iso()),
        )

    @staticmethod
    def _maintenance_due(last_vacuum: str | None, *, interval_days: int) -> bool:
        if last_vacuum is None or not last_vacuum.strip():
            return True
        try:
            parsed = datetime.fromisoformat(last_vacuum)
        except ValueError:
            return True
        return datetime.now(UTC) - parsed >= timedelta(days=interval_days)

    @staticmethod
    def _rebuild_sql() -> dict[str, str]:
        return {
            "document_chunks_fts": """
                INSERT INTO document_chunks_fts (document_type, document_id, chunk_id, title, chunk_text)
                SELECT
                    d.document_type,
                    c.document_id,
                    c.id,
                    d.title,
                    c.chunk_text
                FROM document_chunks AS c
                JOIN documents AS d ON d.id = c.document_id
                WHERE d.deleted_at IS NULL
            """.strip(),
            "file_chunks_fts": """
                INSERT INTO file_chunks_fts (document_type, document_id, chunk_id, path, chunk_text)
                SELECT
                    d.document_type,
                    c.document_id,
                    c.id,
                    c.path,
                    c.chunk_text
                FROM file_chunks AS c
                JOIN documents AS d ON d.id = c.document_id
                WHERE d.deleted_at IS NULL
            """.strip(),
            "memory_facts_fts": """
                INSERT INTO memory_facts_fts (fact_id, content)
                SELECT id, content
                FROM memory_facts
                WHERE status != 'deleted'
            """.strip(),
        }

    def _rebuild_search_indexes(self, connection: sqlite3.Connection) -> list[str]:
        rebuilt: list[str] = []
        for table, sql in self._rebuild_sql().items():
            if not self._table_exists(connection, table):
                continue
            connection.execute(f"DELETE FROM {table}")
            connection.execute(sql)
            rebuilt.append(table)
        return rebuilt
