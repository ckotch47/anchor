from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.cli import config_command


class ConfigCliTest(unittest.TestCase):
    def test_config_get_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        config_command("get")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "config.get")
        self.assertEqual(payload["data"]["config_path"], str(config_path))

    def test_config_set_updates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo"):
                        config_command("set", section="runtime", key="default_view", value="full")
                    with patch("typer.echo") as echo_mock:
                        config_command("get")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertEqual(payload["data"]["config"]["runtime"]["default_view"], "full")

    def test_config_set_parses_false_as_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo"):
                        config_command("set", section="runtime", key="offline_only", value="false")
                    with patch("typer.echo") as echo_mock:
                        config_command("get")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["data"]["config"]["runtime"]["offline_only"])

    def test_config_set_invalid_section_emits_machine_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            config_command("set", section="bad", key="default_view", value="full")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")
