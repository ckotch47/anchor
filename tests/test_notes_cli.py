from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer import Exit

from anchor.cli import notes_add, notes_get, notes_list, notes_search


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
        self.assertTrue(add_payload["data"]["note"]["pinned"])
        self.assertTrue(list_payload["ok"])
        self.assertEqual(list_payload["command"], "notes.list")
        self.assertEqual(list_payload["data"]["count"], 1)
        self.assertEqual(list_payload["data"]["notes"][0]["id"], note_id)
        self.assertTrue(get_payload["ok"])
        self.assertEqual(get_payload["command"], "notes.get")
        self.assertEqual(get_payload["data"]["note"]["id"], note_id)

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
