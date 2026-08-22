from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.cli import health


class HealthCliTest(unittest.TestCase):
    def test_health_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            database_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=database_path).apply_pending()
            before = {
                path.name: (path.stat().st_size, path.stat().st_mtime_ns)
                for path in Path(tmpdir).iterdir()
            }
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    with patch("typer.echo") as echo_mock:
                        health()
            after = {
                path.name: (path.stat().st_size, path.stat().st_mtime_ns)
                for path in Path(tmpdir).iterdir()
            }

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "health")
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertEqual(payload["meta"]["view"], "compact")
        self.assertNotIn("profile", payload["meta"])
        self.assertEqual(before, after)

    def test_health_does_not_create_or_migrate_a_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.toml"
            database_path = root / "anchor.sqlite3"
            before = set(root.iterdir())
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit) as raised:
                            health()
            after = set(root.iterdir())
            self.assertFalse(database_path.exists())

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["ready"])
        self.assertEqual(payload["data"]["status"], "error")
        self.assertEqual(before, after)

    def test_health_rejects_unexpected_migration_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            database_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=database_path).apply_pending()
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (999, 'unexpected', 'unknown', '2026-08-20T00:00:00Z', 'applied')"
                )
                connection.commit()
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            health()

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["data"]["ready"])
        self.assertEqual(payload["data"]["unexpected_migrations"], [999])

    def test_health_rejects_non_applied_migration_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            database_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=database_path).apply_pending()
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("UPDATE schema_migrations SET status = 'failed' WHERE version = 13")
                connection.commit()
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            health()

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["data"]["ready"])
        self.assertEqual(payload["data"]["checks"]["migrations"], "error")

    def test_health_migration_failure_emits_machine_error(self) -> None:
        with patch("anchor.cli.build_container", side_effect=RuntimeError("boom")):
            with patch("typer.echo") as echo_mock:
                with self.assertRaises(Exit):
                    health()

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "health")
        self.assertEqual(payload["error"]["code"], "DB_MIGRATION_FAILED")
