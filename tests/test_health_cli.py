from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.exceptions import Exit

from anchor.cli import health


class HealthCliTest(unittest.TestCase):
    def test_health_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.adapters.sqlite_migration_repository.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        health()

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "health")
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertEqual(payload["meta"]["view"], "compact")

    def test_health_migration_failure_emits_machine_error(self) -> None:
        with patch("anchor.cli.build_container", side_effect=RuntimeError("boom")):
            with patch("typer.echo") as echo_mock:
                with self.assertRaises(Exit):
                    health()

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "health")
        self.assertEqual(payload["error"]["code"], "DB_MIGRATION_FAILED")
