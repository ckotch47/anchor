from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.mcp_server import (
    files_get,
    files_index,
    files_list,
    files_search,
    history_append,
    history_search,
    mcp_app,
    notes_add,
    notes_list,
    notes_search,
    tasks_add,
    tasks_list,
    tasks_search,
)


class McpServerTest(unittest.TestCase):
    def test_mcp_exposes_core_tools(self) -> None:
        async def run() -> list[str]:
            tools = await mcp_app.list_tools()
            return [tool.name for tool in tools]

        tool_names = asyncio.run(run())

        self.assertIn("health", tool_names)
        self.assertIn("search", tool_names)
        self.assertIn("notes_add", tool_names)
        self.assertIn("history_append", tool_names)
        self.assertIn("history_update", tool_names)
        self.assertIn("history_search", tool_names)
        self.assertIn("history_delete", tool_names)
        self.assertIn("tasks_add", tool_names)
        self.assertIn("files_index", tool_names)
        self.assertIn("files_get", tool_names)
        self.assertIn("files_list", tool_names)
        self.assertIn("files_search", tool_names)

    def test_mcp_view_full_returns_full_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    notes_add(title="Note", body="Body text", source="cli")
                    tasks_add(title="Task", body="Task body", project="repo-a")
                    history_append(entry_type="deploy", payload="Deploy completed", project="repo-a")
                    files_index(roots=[str(root)], project="repo-a")

                    notes_list_payload = notes_list(view="full")
                    notes_search_payload = notes_search(query="Body", view="full")
                    tasks_list_payload = tasks_list(project="repo-a", view="full")
                    tasks_search_payload = tasks_search(query="Task", project="repo-a", view="full")
                    history_search_payload = history_search(query="Deploy", project="repo-a", view="full")
                    files_get_payload = files_get(path=str((root / "app.py").resolve()), project="repo-a", view="full")
                    files_list_payload = files_list(project="repo-a", view="full")
                    files_search_payload = files_search(query="greet", project="repo-a", view="full", explain=True)

        self.assertIn("body", notes_list_payload["data"]["notes"][0])
        self.assertIn("body", notes_search_payload["data"]["results"][0]["note"])
        self.assertIn("body", tasks_list_payload["data"]["tasks"][0])
        self.assertIn("body", tasks_search_payload["data"]["results"][0]["task"])
        self.assertIn("payload", history_search_payload["data"]["results"][0]["history"])
        self.assertIn("content_hash", files_get_payload["data"]["file"])
        self.assertIn("content_hash", files_list_payload["data"]["files"][0])
        self.assertIn("content_hash", files_search_payload["data"]["results"][0]["file"])
        self.assertIn("stats", files_search_payload["data"])
        self.assertEqual(notes_list_payload["meta"]["view"], "full")
        self.assertEqual(notes_search_payload["meta"]["view"], "full")
        self.assertEqual(tasks_list_payload["meta"]["view"], "full")
        self.assertEqual(tasks_search_payload["meta"]["view"], "full")
        self.assertEqual(history_search_payload["meta"]["view"], "full")
        self.assertEqual(files_get_payload["meta"]["view"], "full")
        self.assertEqual(files_list_payload["meta"]["view"], "full")
        self.assertEqual(files_search_payload["meta"]["view"], "full")

    def test_mcp_invalid_view_returns_machine_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = notes_list(view="detailed")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "notes.list")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGS")
        self.assertIn("compact", payload["error"]["message"])
