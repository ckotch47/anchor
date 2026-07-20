from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.mcp_server import (
    files_delete,
    files_get,
    files_index,
    files_list,
    files_search,
    history_append,
    history_delete,
    history_search,
    history_update,
    links_add,
    links_delete,
    links_list,
    mcp_app,
    notes_add,
    notes_list,
    notes_search,
    notes_update,
    search,
    tasks_add,
    tasks_delete,
    tasks_done,
    tasks_get,
    tasks_list,
    tasks_search,
    tasks_update,
)


def _structured(result: object) -> dict[str, object]:
    structured = getattr(result, "structuredContent", None)
    assert isinstance(structured, dict)
    return structured


class McpServerTest(unittest.TestCase):
    def test_mcp_exposes_core_tools(self) -> None:
        async def run() -> list[str]:
            tools = await mcp_app.list_tools()
            return [tool.name for tool in tools]

        tool_names = asyncio.run(run())

        self.assertIn("health", tool_names)
        self.assertIn("db_compact", tool_names)
        self.assertIn("search", tool_names)
        self.assertIn("notes_add", tool_names)
        self.assertIn("history_append", tool_names)
        self.assertIn("memory_evidence", tool_names)
        self.assertIn("memory_scenarios", tool_names)
        self.assertIn("memory_conflicts", tool_names)
        self.assertIn("memory_metrics", tool_names)
        self.assertIn("memory_flush", tool_names)
        self.assertIn("history_update", tool_names)
        self.assertIn("history_search", tool_names)
        self.assertIn("history_delete", tool_names)
        self.assertIn("tasks_add", tool_names)
        self.assertIn("tasks_get", tool_names)
        self.assertIn("files_index", tool_names)
        self.assertIn("files_get", tool_names)
        self.assertIn("files_delete", tool_names)
        self.assertIn("files_list", tool_names)
        self.assertIn("files_search", tool_names)
        self.assertIn("links_add", tool_names)
        self.assertIn("links_delete", tool_names)
        self.assertIn("links_list", tool_names)

    def test_mcp_view_full_returns_full_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    note_payload = _structured(notes_add(title="Note", body="Body text", source="cli"))
                    task_payload = _structured(tasks_add(title="Task", body="Task body", project="repo-a"))
                    history_payload = _structured(
                        history_append(entry_type="deploy", payload="Deploy completed", project="repo-a")
                    )
                    files_index(roots=[str(root)], project="repo-a")
                    file_bootstrap_payload = files_get(path=str((root / "app.py").resolve()), project="repo-a", view="full")

                    note_id = note_payload["data"]["note"]["id"]
                    task_id = task_payload["data"]["task"]["id"]
                    history_id = history_payload["data"]["history"]["id"]
                    file_id = _structured(file_bootstrap_payload)["data"]["file"]["id"]

                    links_add(source_id=note_id, target_id=task_id, relation_type="references")
                    links_add(source_id=task_id, target_id=history_id, relation_type="references")
                    links_add(source_id=file_id, target_id=note_id, relation_type="related")

                    notes_list_payload = notes_list(view="full")
                    task_get_payload = tasks_get(
                        task_id=task_id,
                        project="repo-a",
                        view="full",
                    )
                    notes_search_payload = notes_search(query="Body", view="full")
                    tasks_list_payload = tasks_list(project="repo-a", view="full")
                    tasks_search_payload = tasks_search(query="Task", project="repo-a", view="full")
                    history_search_payload = history_search(query="Deploy", project="repo-a", view="full")
                    files_get_payload = files_get(path=str((root / "app.py").resolve()), project="repo-a", view="full")
                    files_list_payload = files_list(project="repo-a", view="full")
                    files_search_payload = files_search(query="greet", project="repo-a", view="full", explain=True)

        self.assertEqual(notes_list_payload.content, [])
        self.assertEqual(task_get_payload.content, [])
        self.assertEqual(notes_search_payload.content, [])
        self.assertEqual(tasks_list_payload.content, [])
        self.assertEqual(tasks_search_payload.content, [])
        self.assertEqual(history_search_payload.content, [])
        self.assertEqual(files_get_payload.content, [])
        self.assertEqual(files_list_payload.content, [])
        self.assertEqual(files_search_payload.content, [])
        self.assertIn("body", _structured(notes_list_payload)["data"]["notes"][0])
        self.assertIn("body", _structured(task_get_payload)["data"]["task"])
        self.assertIn("body", _structured(notes_search_payload)["data"]["results"][0]["note"])
        self.assertIn("body", _structured(tasks_list_payload)["data"]["tasks"][0])
        self.assertIn("body", _structured(tasks_search_payload)["data"]["results"][0]["task"])
        self.assertIn("payload", _structured(history_search_payload)["data"]["results"][0]["history"])
        self.assertIn("content_hash", _structured(files_get_payload)["data"]["file"])
        self.assertIn("content_hash", _structured(files_list_payload)["data"]["files"][0])
        self.assertIn("content_hash", _structured(files_search_payload)["data"]["results"][0]["file"])
        self.assertIn("stats", _structured(files_search_payload)["data"])
        self.assertGreater(len(_structured(task_get_payload)["data"]["task"]["links"]), 0)
        self.assertGreater(len(_structured(notes_search_payload)["data"]["results"][0]["note"]["links"]), 0)
        self.assertGreater(len(_structured(tasks_search_payload)["data"]["results"][0]["task"]["links"]), 0)
        self.assertGreater(len(_structured(history_search_payload)["data"]["results"][0]["history"]["links"]), 0)
        self.assertGreater(len(_structured(files_get_payload)["data"]["file"]["links"]), 0)
        self.assertGreater(len(_structured(files_search_payload)["data"]["results"][0]["file"]["links"]), 0)
        self.assertEqual(_structured(notes_list_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(task_get_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(notes_search_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(tasks_list_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(tasks_search_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(history_search_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(files_get_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(files_list_payload)["meta"]["view"], "full")
        self.assertEqual(_structured(files_search_payload)["meta"]["view"], "full")

    def test_mcp_notes_update_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = notes_update(note_id=uuid7_str(), title="Missing", project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "notes.update")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_tasks_update_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = tasks_update(task_id=uuid7_str(), title="Missing task", project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "tasks.update")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_tasks_done_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = tasks_done(task_id=uuid7_str(), project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "tasks.done")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_tasks_delete_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = tasks_delete(task_id=uuid7_str(), project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "tasks.delete")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_history_update_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = history_update(history_id=uuid7_str(), payload="Missing history", project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "history.update")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_history_delete_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = history_delete(history_id=uuid7_str(), project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "history.delete")
        self.assertEqual(structured["error"]["code"], "NOT_FOUND")

    def test_mcp_notes_and_tasks_list_expose_next_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    notes_add(title="Note one", body="Body one", source="cli")
                    notes_add(title="Note two", body="Body two", source="cli")
                    tasks_add(title="Task one", body="Body one", project="repo-a")
                    tasks_add(title="Task two", body="Body two", project="repo-a")

                    notes_payload = notes_list(project=None, limit=1)
                    tasks_payload = tasks_list(project="repo-a", limit=1)

        self.assertEqual(notes_payload.content, [])
        self.assertEqual(tasks_payload.content, [])
        self.assertTrue(_structured(notes_payload)["ok"])
        self.assertEqual(_structured(notes_payload)["command"], "notes.list")
        self.assertIn("next_cursor", _structured(notes_payload)["data"])
        self.assertTrue(_structured(tasks_payload)["ok"])
        self.assertEqual(_structured(tasks_payload)["command"], "tasks.list")
        self.assertIn("next_cursor", _structured(tasks_payload)["data"])

    def test_mcp_tasks_get_returns_full_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    created = _structured(tasks_add(title="Task one", body="Body one", project="repo-a"))
                    task_id = created["data"]["task"]["id"]
                    payload = tasks_get(task_id=task_id, project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["command"], "tasks.get")
        self.assertEqual(structured["data"]["task"]["id"], task_id)
        self.assertEqual(structured["data"]["task"]["title"], "Task one")

    def test_mcp_files_delete_removes_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    files_index(roots=[str(root)], project="repo-a")
                    deleted_payload = files_delete(path=str((root / "app.py").resolve()), project="repo-a")
                    list_payload = files_list(project="repo-a")
                    search_payload = files_search(query="greet", project="repo-a")

        self.assertEqual(deleted_payload.content, [])
        self.assertEqual(list_payload.content, [])
        self.assertEqual(search_payload.content, [])
        self.assertTrue(_structured(deleted_payload)["ok"])
        self.assertEqual(_structured(deleted_payload)["command"], "files.delete")
        self.assertEqual(_structured(deleted_payload)["data"]["file"]["path"], str((root / "app.py").resolve()))
        self.assertEqual(_structured(list_payload)["data"]["count"], 0)
        self.assertEqual(_structured(search_payload)["data"]["count"], 0)
        self.assertNotIn("query", _structured(search_payload)["data"])

    def test_mcp_files_get_without_identifier_returns_invalid_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = files_get(project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "files.get")
        self.assertEqual(structured["error"]["code"], "INVALID_ARGS")

    def test_mcp_files_delete_without_identifier_returns_invalid_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = files_delete(project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "files.delete")
        self.assertEqual(structured["error"]["code"], "INVALID_ARGS")

    def test_mcp_files_list_invalid_limit_returns_invalid_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = files_list(project="repo-a", limit=0)

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "files.list")
        self.assertEqual(structured["error"]["code"], "INVALID_ARGS")

    def test_mcp_files_search_empty_query_returns_invalid_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = files_search(query=" ", project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["command"], "files.search")
        self.assertEqual(structured["error"]["code"], "INVALID_ARGS")

    def test_mcp_search_compact_omits_query_and_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    notes_add(title="Note", body="Body text", source="cli", project="repo-a")
                    tasks_add(title="Task", body="Task body", project="repo-a")
                    payload = search(query="Body", types=["notes", "tasks"], project="repo-a")

        self.assertEqual(payload.content, [])
        structured = _structured(payload)
        self.assertTrue(structured["ok"])
        self.assertEqual(structured["command"], "search")
        self.assertNotIn("query", structured["data"])
        self.assertEqual(structured["data"]["count"], 2)
        self.assertNotIn("attributes", structured["data"]["results"][0])
        self.assertNotIn("config_path", structured["meta"])
        self.assertNotIn("project", structured["meta"])
        self.assertNotIn("projects", structured["meta"])
        self.assertNotIn("types", structured["meta"])
        self.assertNotIn("profile", structured["meta"])

    def test_mcp_links_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    source = _structured(notes_add(title="Source", body="Body text", source="cli", project="repo-a"))
                    target = _structured(notes_add(title="Target", body="Body text", source="cli", project="repo-a"))
                    source_id = source["data"]["note"]["id"]
                    target_id = target["data"]["note"]["id"]
                    add_payload = links_add(source_id=source_id, target_id=target_id, relation_type="references")
                    list_payload = links_list(source_id=source_id)
                    delete_payload = links_delete(source_id=source_id, target_id=target_id, relation_type="references")

        self.assertEqual(add_payload.content, [])
        self.assertEqual(list_payload.content, [])
        self.assertEqual(delete_payload.content, [])
        self.assertTrue(_structured(add_payload)["ok"])
        self.assertEqual(_structured(add_payload)["command"], "links.add")
        self.assertEqual(_structured(add_payload)["data"]["link"]["source_id"], source_id)
        self.assertEqual(_structured(list_payload)["command"], "links.list")
        self.assertEqual(_structured(list_payload)["data"]["count"], 1)
        self.assertEqual(_structured(delete_payload)["command"], "links.delete")
        self.assertTrue(_structured(delete_payload)["data"]["deleted"])

    def test_mcp_files_list_exposes_next_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
            (root / "beta.py").write_text("def beta():\n    return 'beta'\n", encoding="utf-8")

            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    files_index(roots=[str(root)], project="repo-a")
                    list_payload = files_list(project="repo-a", limit=1)

        self.assertEqual(list_payload.content, [])
        self.assertTrue(_structured(list_payload)["ok"])
        self.assertEqual(_structured(list_payload)["command"], "files.list")
        self.assertIn("next_cursor", _structured(list_payload)["data"])

    def test_mcp_invalid_view_returns_machine_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            db_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=db_path):
                    payload = notes_list(view="detailed")

        self.assertEqual(payload.content, [])
        self.assertFalse(_structured(payload)["ok"])
        self.assertEqual(_structured(payload)["command"], "notes.list")
        self.assertEqual(_structured(payload)["error"]["code"], "INVALID_ARGS")
        self.assertIn("compact", _structured(payload)["error"]["message"])
