from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.cli import history_append, history_delete, history_search, history_update


class HistoryCliTest(unittest.TestCase):
    def test_history_append_and_search_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as append_echo_mock:
                        history_append(
                            entry_type="deploy",
                            payload="Deploy step completed",
                            project="repo-a",
                            metatags='{"topic":"ops"}',
                        )

                    append_payload = json.loads(append_echo_mock.call_args.args[0])
                    history_id = append_payload["data"]["history"]["id"]

                    with patch("typer.echo") as search_echo_mock:
                        history_search(query="Deploy", project="repo-a", view="full")

        search_payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertTrue(append_payload["ok"])
        self.assertEqual(append_payload["command"], "history.append")
        self.assertEqual(append_payload["data"]["history"]["id"], history_id)
        self.assertEqual(append_payload["data"]["history"]["project"], "repo-a")
        self.assertEqual(append_payload["data"]["history"]["metatags"], {"topic": "ops"})
        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["command"], "history.search")
        self.assertEqual(search_payload["data"]["count"], 1)
        self.assertEqual(search_payload["data"]["results"][0]["history"]["id"], history_id)
        self.assertIn("payload", search_payload["data"]["results"][0]["history"])

    def test_history_update_and_delete_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as append_echo_mock:
                        history_append(
                            entry_type="deploy",
                            payload="Deploy step completed",
                            project="repo-a",
                        )

                    history_id = json.loads(append_echo_mock.call_args.args[0])["data"]["history"]["id"]

                    with patch("typer.echo") as update_echo_mock:
                        history_update(history_id=history_id, payload="Deploy step updated", project="repo-a")

                    with patch("typer.echo") as delete_echo_mock:
                        history_delete(history_id=history_id, project="repo-a")

        update_payload = json.loads(update_echo_mock.call_args.args[0])
        delete_payload = json.loads(delete_echo_mock.call_args.args[0])
        self.assertTrue(update_payload["ok"])
        self.assertEqual(update_payload["command"], "history.update")
        self.assertEqual(update_payload["data"]["history"]["payload"], "Deploy step updated")
        self.assertNotIn("project", update_payload["meta"])
        self.assertTrue(delete_payload["ok"])
        self.assertEqual(delete_payload["command"], "history.delete")
        self.assertEqual(delete_payload["data"]["history"]["id"], history_id)
        self.assertNotIn("project", delete_payload["meta"])
