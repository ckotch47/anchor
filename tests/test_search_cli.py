from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.cli import notes_add, search, tasks_add


class SearchCliTest(unittest.TestCase):
    def test_search_combines_notes_and_tasks_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo"):
                        notes_add(title="Deploy note", body="deploy note body", source="cli", project="repo-a")
                    with patch("typer.echo"):
                        tasks_add(title="Deploy task", body="deploy task body", project="repo-a")

                    with patch("typer.echo") as search_echo_mock:
                        search(query="deploy", types="notes,tasks", project="repo-a", view="full", explain=True)

        payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "search")
        self.assertEqual(payload["data"]["count"], 2)
        self.assertEqual(payload["data"]["query"]["query"], "deploy")
        self.assertEqual(payload["data"]["query"]["types"], ["notes", "tasks"])
        self.assertIsNotNone(payload["data"]["stats"])
        self.assertEqual({hit["entity_type"] for hit in payload["data"]["results"]}, {"notes", "tasks"})

    def test_search_compact_omits_query_and_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo"):
                        notes_add(title="Deploy note", body="deploy note body", source="cli", project="repo-a")
                    with patch("typer.echo"):
                        tasks_add(title="Deploy task", body="deploy task body", project="repo-a")

                    with patch("typer.echo") as search_echo_mock:
                        search(query="deploy", types="notes,tasks", project="repo-a")

        payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "search")
        self.assertNotIn("query", payload["data"])
        self.assertEqual(payload["data"]["count"], 2)
        self.assertNotIn("attributes", payload["data"]["results"][0])
        self.assertNotIn("config_path", payload["meta"])
        self.assertNotIn("projects", payload["meta"])
        self.assertNotIn("types", payload["meta"])
        self.assertNotIn("profile", payload["meta"])
