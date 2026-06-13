from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.cli import notes_add, notes_delete, notes_get, notes_list, notes_search, notes_update


class NotesCliTest(unittest.TestCase):
    def test_notes_add_list_and_get_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        notes_add(title="First note", body="Body text", source="cli", pinned=True)

                    add_payload = json.loads(add_echo_mock.call_args.args[0])
                    note_id = add_payload["data"]["note"]["id"]

                    with patch("typer.echo") as list_echo_mock:
                        notes_list()

                    list_payload = json.loads(list_echo_mock.call_args.args[0])
                    with patch("typer.echo") as get_echo_mock:
                        notes_get(note_id=note_id)

        get_payload = json.loads(get_echo_mock.call_args.args[0])
        self.assertTrue(add_payload["ok"])
        self.assertEqual(add_payload["command"], "notes.add")
        self.assertEqual(add_payload["data"]["note"]["title"], "First note")
        self.assertEqual(add_payload["data"]["note"]["project"], "workspace")
        self.assertTrue(add_payload["data"]["note"]["pinned"])
        self.assertTrue(list_payload["ok"])
        self.assertEqual(list_payload["command"], "notes.list")
        self.assertEqual(list_payload["data"]["count"], 1)
        self.assertEqual(list_payload["data"]["notes"][0]["id"], note_id)
        self.assertEqual(list_payload["data"]["notes"][0]["project"], "workspace")
        self.assertNotIn("body", list_payload["data"]["notes"][0])
        self.assertTrue(get_payload["ok"])
        self.assertEqual(get_payload["command"], "notes.get")
        self.assertEqual(get_payload["data"]["note"]["id"], note_id)
        self.assertEqual(get_payload["data"]["note"]["project"], "workspace")

    def test_notes_update_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        notes_add(title="First note", body="Body text", source="cli")
                    note_id = json.loads(add_echo_mock.call_args.args[0])["data"]["note"]["id"]

                    with patch("typer.echo") as update_echo_mock:
                        notes_update(note_id=note_id, title="Updated note", body="Updated body")

        update_payload = json.loads(update_echo_mock.call_args.args[0])
        self.assertTrue(update_payload["ok"])
        self.assertEqual(update_payload["command"], "notes.update")
        self.assertEqual(update_payload["data"]["note"]["title"], "Updated note")
        self.assertEqual(update_payload["data"]["note"]["body"], "Updated body")
        self.assertEqual(update_payload["data"]["note"]["project"], "workspace")

    def test_notes_add_supports_project_and_metatags_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        notes_add(
                            title="Scoped note",
                            body="Body text",
                            source="cli",
                            project="repo-a",
                            metatags='{"topic":"rag","priority":1}',
                        )

                    add_payload = json.loads(add_echo_mock.call_args.args[0])
                    note_id = add_payload["data"]["note"]["id"]

                    with patch("typer.echo") as list_echo_mock:
                        notes_list(project="repo-a")

                    list_payload = json.loads(list_echo_mock.call_args.args[0])
                    with patch("typer.echo") as get_echo_mock:
                        notes_get(note_id=note_id, project="repo-a")

                    with patch("typer.echo") as search_echo_mock:
                        notes_search(query="Scoped", project="repo-a")

        get_payload = json.loads(get_echo_mock.call_args.args[0])
        search_payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertEqual(add_payload["data"]["note"]["project"], "repo-a")
        self.assertEqual(add_payload["data"]["note"]["metatags"], {"topic": "rag", "priority": 1})
        self.assertEqual(list_payload["meta"]["project"], "repo-a")
        self.assertEqual(list_payload["data"]["notes"][0]["project"], "repo-a")
        self.assertEqual(get_payload["data"]["note"]["project"], "repo-a")
        self.assertEqual(search_payload["meta"]["project"], "repo-a")

    def test_notes_add_empty_payload_emits_machine_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            notes_add(title=" ", body=" ", source="cli")

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "notes")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")

    def test_notes_search_finds_matching_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo"):
                        notes_add(title="First note", body="Use FTS search for notes", source="cli")
                    with patch("typer.echo"):
                        notes_add(title="Second note", body="Something unrelated", source="cli")

                    with patch("typer.echo") as echo_mock:
                        notes_search(query='FTS * (search)', limit=10)

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "notes.search")
        self.assertEqual(payload["data"]["query"], "FTS * (search)")
        self.assertEqual(payload["data"]["count"], 1)
        self.assertEqual(payload["data"]["results"][0]["note"]["title"], "First note")
        self.assertIn("FTS", payload["data"]["results"][0]["snippet"])

    def test_notes_search_rejects_empty_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=Path(tmpdir) / "anchor.sqlite3"):
                    with patch("typer.echo") as echo_mock:
                        with self.assertRaises(Exit):
                            notes_search(query=" ", limit=10)

        payload = json.loads(echo_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "notes")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")

    def test_notes_delete_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as add_echo_mock:
                        notes_add(title="Delete me", body="Body text", source="cli", project="repo-a")
                    note_id = json.loads(add_echo_mock.call_args.args[0])["data"]["note"]["id"]

                    with patch("typer.echo") as delete_echo_mock:
                        notes_delete(note_id=note_id, project="repo-a")

        delete_payload = json.loads(delete_echo_mock.call_args.args[0])
        self.assertTrue(delete_payload["ok"])
        self.assertEqual(delete_payload["command"], "notes.delete")
        self.assertEqual(delete_payload["data"]["note"]["id"], note_id)
        self.assertEqual(delete_payload["meta"]["project"], "repo-a")
