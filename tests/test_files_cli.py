from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.cli import files_index, files_search


class FilesCliTest(unittest.TestCase):
    def test_files_index_and_search_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    with patch("typer.echo") as index_echo_mock:
                        files_index(root=[str(root)], project="repo-a")
                    with patch("typer.echo") as search_echo_mock:
                        files_search(query="greet", project="repo-a")

        index_payload = json.loads(index_echo_mock.call_args.args[0])
        search_payload = json.loads(search_echo_mock.call_args.args[0])
        self.assertTrue(index_payload["ok"])
        self.assertEqual(index_payload["command"], "files.index")
        self.assertEqual(index_payload["data"]["indexed"], 1)
        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["command"], "files.search")
        self.assertEqual(search_payload["data"]["count"], 1)
        self.assertEqual(search_payload["data"]["results"][0]["file"]["path"], str((root / "app.py").resolve()))
