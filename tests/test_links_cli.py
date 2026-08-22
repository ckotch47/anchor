from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from anchor.cli import app, links_add, links_delete, links_list
from anchor.cli_notes import notes_add


class LinksCliTest(unittest.TestCase):
    def test_missing_project_uses_machine_error_envelope(self) -> None:
        result = CliRunner().invoke(
            app,
            [
                "links",
                "add",
                "--source-id",
                "source",
                "--target-id",
                "target",
                "--relation-type",
                "references",
            ],
        )

        self.assertEqual(result.exit_code, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "links.add")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")

    def test_links_add_list_delete_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as source_echo_mock:
                        notes_add(title="Source", body="Body", source="cli", project="repo-a")
                    with patch("typer.echo") as target_echo_mock:
                        notes_add(title="Target", body="Body", source="cli", project="repo-a")

                    source_payload = json.loads(source_echo_mock.call_args.args[0])
                    target_payload = json.loads(target_echo_mock.call_args.args[0])
                    source_id = source_payload["data"]["note"]["id"]
                    target_id = target_payload["data"]["note"]["id"]

                    with patch("typer.echo") as add_echo_mock:
                        links_add(project="repo-a", source_id=source_id, target_id=target_id, relation_type="references")
                    with patch("typer.echo") as list_echo_mock:
                        links_list(project="repo-a", source_id=source_id)
                    with patch("typer.echo") as delete_echo_mock:
                        links_delete(project="repo-a", source_id=source_id, target_id=target_id, relation_type="references")

        add_payload = json.loads(add_echo_mock.call_args.args[0])
        list_payload = json.loads(list_echo_mock.call_args.args[0])
        delete_payload = json.loads(delete_echo_mock.call_args.args[0])

        self.assertTrue(add_payload["ok"])
        self.assertEqual(add_payload["command"], "links.add")
        self.assertEqual(add_payload["data"]["link"]["source_id"], source_id)
        self.assertEqual(add_payload["data"]["link"]["target_id"], target_id)

        self.assertTrue(list_payload["ok"])
        self.assertEqual(list_payload["command"], "links.list")
        self.assertEqual(list_payload["data"]["count"], 1)
        self.assertEqual(list_payload["data"]["links"][0]["relation_type"], "references")

        self.assertTrue(delete_payload["ok"])
        self.assertEqual(delete_payload["command"], "links.delete")
        self.assertTrue(delete_payload["data"]["deleted"])
