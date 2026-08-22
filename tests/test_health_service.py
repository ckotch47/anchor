from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from anchor.adapters.sqlite_health_repository import SqliteHealthRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.adapters.sqlite_support import configure_connection, connect_trusted_sqlite
from anchor.application.system.health_service import HealthService
from anchor.config import AppConfig


class HealthServiceTest(unittest.TestCase):
    def test_health_reads_side_effect_free_snapshot(self) -> None:
        snapshot_port = Mock()
        snapshot_port.snapshot.return_value = {
            "ready": True,
            "status": "ok",
            "checks": {"storage": "ok", "integrity": "ok", "migrations": "ok"},
            "index_error_count": 0,
            "pending_migrations": [],
        }
        service = HealthService(config=AppConfig.default(), snapshot_port=snapshot_port)

        result = service.health()

        snapshot_port.snapshot.assert_called_once()
        self.assertTrue(result.ready)
        self.assertEqual(result.mode, "offline-only")

    def test_health_snapshot_sees_committed_live_wal_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=database_path).apply_pending()
            writer = connect_trusted_sqlite(database_path)
            configure_connection(writer, 250, database_path=database_path)
            try:
                writer.execute(
                    "INSERT INTO schema_migrations VALUES (999, 'unexpected', 'unknown', '2026-08-20T00:00:00Z', 'applied')"
                )
                writer.commit()

                snapshot = SqliteHealthRepository(database_path).snapshot()
            finally:
                writer.close()

        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["unexpected_migrations"], [999])
