from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.cli import db_command


class DbCliTest(unittest.TestCase):
    def test_db_migrate_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as echo_mock:
                        db_command("migrate")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "db.migrate")
        self.assertEqual(payload["data"]["database_path"], str(db_path))
        self.assertEqual(payload["data"]["current_version"], 7)
        self.assertIn("checkpoint", payload["data"])
        self.assertNotIn("profile", payload["meta"])

    def test_db_compact_emits_json(self) -> None:
        with patch("anchor.cli.build_container") as build_container_mock:
            build_container_mock.return_value.config.runtime.default_view = "compact"
            build_container_mock.return_value.profile_name = None
            maintenance_service = build_container_mock.return_value.maintenance_service
            maintenance_service.compact.return_value.model_dump.return_value = {
                "purged_documents": 3,
                "rebuilt_indexes": ["document_chunks_fts", "file_chunks_fts"],
                "vacuumed": True,
                "checkpoint": {"busy": 0, "log": 0, "checkpointed": 0},
            }
            with patch("typer.echo") as echo_mock:
                db_command(
                    "compact",
                    retention_days=14,
                    rebuild_search_indexes=True,
                    vacuum=True,
                    checkpoint=True,
                )

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "db.compact")
        self.assertEqual(payload["data"]["purged_documents"], 3)
        self.assertNotIn("profile", payload["meta"])
        maintenance_service.compact.assert_called_once()

    def test_db_migrate_failure_emits_machine_error(self) -> None:
        container = patch("anchor.cli.build_container")
        with container as build_container_mock:
            build_container_mock.return_value.migration_service.migrate.side_effect = RuntimeError("boom")
            with patch("typer.echo") as echo_mock, self.assertRaises(Exit):
                db_command("migrate")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "db")
        self.assertEqual(payload["error"]["code"], "DB_MIGRATION_FAILED")

    def test_db_invalid_action_emits_machine_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("typer.echo") as echo_mock:
                    with self.assertRaises(Exit):
                        db_command("bad-action")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")
