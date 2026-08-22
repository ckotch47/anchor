from __future__ import annotations

import sqlite3
from pathlib import Path

from anchor.adapters.sqlite_migration_repository import MIGRATIONS
from anchor.adapters.sqlite_support import connect_trusted_sqlite_read_only, sqlite_read_lock


class SqliteHealthRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def snapshot(self) -> dict[str, object]:
        try:
            with sqlite_read_lock(self._database_path):
                connection = connect_trusted_sqlite_read_only(self._database_path)
                connection.row_factory = sqlite3.Row
                try:
                    connection.execute("PRAGMA query_only = ON")
                    connection.execute("PRAGMA busy_timeout = 250")
                    quick_check = connection.execute("PRAGMA quick_check(1)").fetchone()
                    integrity_ok = quick_check is not None and str(quick_check[0]).lower() == "ok"
                    applied = {
                        int(row["version"]): (str(row["checksum"]), str(row["status"]))
                        for row in connection.execute("SELECT version, checksum, status FROM schema_migrations")
                    }
                    expected = {migration.version: migration.checksum for migration in MIGRATIONS}
                    migrations_ok = set(applied) == set(expected) and all(
                        applied.get(version) == (checksum, "applied") for version, checksum in expected.items()
                    )
                    pending = sorted(set(expected) - set(applied))
                    unexpected = sorted(set(applied) - set(expected))
                    index_errors = self._index_error_count(connection)
                finally:
                    connection.close()
        except Exception:
            return {
                "ready": False,
                "status": "error",
                "checks": {"storage": "error", "integrity": "unknown", "migrations": "unknown"},
                "index_error_count": 0,
                "pending_migrations": [],
                "unexpected_migrations": [],
            }
        ready = integrity_ok and migrations_ok and not pending
        status = "ok" if ready and index_errors == 0 else "degraded" if ready else "error"
        return {
            "ready": ready,
            "status": status,
            "checks": {
                "storage": "ok",
                "integrity": "ok" if integrity_ok else "error",
                "migrations": "ok" if migrations_ok and not pending else "error",
            },
            "index_error_count": index_errors,
            "pending_migrations": pending,
            "unexpected_migrations": unexpected,
        }

    @staticmethod
    def _index_error_count(connection: sqlite3.Connection) -> int:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='index_states'"
        ).fetchone()
        if exists is None:
            return 0
        row = connection.execute("SELECT COUNT(*) FROM index_states WHERE state = 'error'").fetchone()
        return int(row[0]) if row is not None else 0
