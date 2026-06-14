from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.cli import tasks_add, tasks_delete, tasks_done, tasks_list, tasks_search, tasks_update


class TasksCliTest(unittest.TestCase):
    def test_tasks_add_list_and_done_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        tasks_add(
                            title="Ship tasks slice",
                            body="Implement tasks commands",
                            project="repo-a",
                            metatags='{"topic":"tasks"}',
                            priority=2,
                            due_at="2026-06-30T00:00:00+00:00",
                            parent_document_id=uuid7_str(),
                        )
                    with patch("typer.echo") as second_add_echo_mock:
                        tasks_add(title="Second task", body="Second body", project="repo-a")

                    add_payload = json.loads(add_echo_mock.call_args.args[0])
                    task_id = add_payload["data"]["task"]["id"]
                    second_task_id = json.loads(second_add_echo_mock.call_args.args[0])["data"]["task"]["id"]

                    with patch("typer.echo") as list_echo_mock:
                        tasks_list(project="repo-a", view="full", limit=1)

                    list_payload = json.loads(list_echo_mock.call_args.args[0])
                    with patch("typer.echo") as done_echo_mock:
                        tasks_done(task_id=task_id, project="repo-a")

        done_payload = json.loads(done_echo_mock.call_args.args[0])
        self.assertTrue(add_payload["ok"])
        self.assertEqual(add_payload["command"], "tasks.add")
        self.assertEqual(add_payload["data"]["task"]["project"], "repo-a")
        self.assertEqual(add_payload["data"]["task"]["metatags"], {"topic": "tasks"})
        self.assertEqual(list_payload["command"], "tasks.list")
        self.assertEqual(list_payload["data"]["count"], 1)
        self.assertEqual(list_payload["data"]["tasks"][0]["id"], second_task_id)
        self.assertEqual(list_payload["data"]["tasks"][0]["title"], "Second task")
        self.assertEqual(list_payload["data"]["tasks"][0]["status"], "open")
        self.assertIn("body", list_payload["data"]["tasks"][0])
        self.assertIn("next_cursor", list_payload["data"])
        self.assertEqual(done_payload["command"], "tasks.done")
        self.assertEqual(done_payload["data"]["task"]["status"], "done")

    def test_tasks_update_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        tasks_add(title="Ship tasks slice", body="Implement tasks commands", project="repo-a")
                    task_id = json.loads(add_echo_mock.call_args.args[0])["data"]["task"]["id"]

                    with patch("typer.echo") as update_echo_mock:
                        tasks_update(
                            task_id=task_id,
                            title="Ship tasks slice v2",
                            priority=5,
                            due_at="2026-07-01T00:00:00+00:00",
                            project="repo-a",
                        )

        update_payload = json.loads(update_echo_mock.call_args.args[0])
        self.assertTrue(update_payload["ok"])
        self.assertEqual(update_payload["command"], "tasks.update")
        self.assertEqual(update_payload["data"]["task"]["title"], "Ship tasks slice v2")
        self.assertEqual(update_payload["data"]["task"]["priority"], 5)
        self.assertEqual(update_payload["data"]["task"]["project"], "repo-a")

    def test_tasks_search_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo"):
                        tasks_add(title="Deploy tasks", body="Add deploy search", project="repo-a")

                    with patch("typer.echo") as search_echo_mock:
                        tasks_search(query="deploy", project="repo-a", view="full")

        search_payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["command"], "tasks.search")
        self.assertEqual(search_payload["data"]["count"], 1)
        self.assertEqual(search_payload["data"]["results"][0]["task"]["title"], "Deploy tasks")
        self.assertIn("snippet", search_payload["data"]["results"][0])
        self.assertIn("body", search_payload["data"]["results"][0]["task"])

    def test_tasks_add_rejects_empty_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            tasks_add(title=" ", body=" ", project="repo-a")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "tasks")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")

    def test_tasks_delete_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        tasks_add(title="Delete me", body="Task body", project="repo-a")
                    task_id = json.loads(add_echo_mock.call_args.args[0])["data"]["task"]["id"]

                    with patch("typer.echo") as delete_echo_mock:
                        tasks_delete(task_id=task_id, project="repo-a")

        delete_payload = json.loads(delete_echo_mock.call_args.args[0])
        self.assertTrue(delete_payload["ok"])
        self.assertEqual(delete_payload["command"], "tasks.delete")
        self.assertEqual(delete_payload["data"]["task"]["id"], task_id)
        self.assertEqual(delete_payload["meta"]["project"], "repo-a")
