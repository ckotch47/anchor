from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anchor.mcp_server import memory_capture, memory_context, memory_recall, memory_search


def _structured(result: object) -> dict[str, object]:
    structured = getattr(result, "structuredContent", None)
    assert isinstance(structured, dict)
    return structured


class MemoryMcpTest(unittest.TestCase):
    def test_capture_and_recall_share_global_memory_across_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            database_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    capture = memory_capture(
                        content="User prefers pytest",
                        fact_type="preference",
                        scope="global",
                        project="repo-a",
                        chat_id="chat-a",
                        evidence_refs=["history-a"],
                        status="active",
                    )
                    recalled = memory_recall(query="pytest", project="repo-b", chat_id="chat-b")
                    searched = memory_search(query="pytest", scope="global", project="repo-b")

        self.assertEqual(_structured(capture)["command"], "memory.capture")
        self.assertEqual(_structured(recalled)["data"]["count"], 1)
        self.assertEqual(_structured(searched)["data"]["count"], 1)

    def test_context_contains_only_current_project_and_global_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            database_path = Path(tmpdir) / "anchor.sqlite3"
            with patch("anchor.config.default_config_path", return_value=config_path):
                with patch("anchor.container.default_database_path", return_value=database_path):
                    memory_capture(
                        content="Global preference",
                        fact_type="preference",
                        scope="global",
                        project="repo-a",
                        evidence_refs=["global"],
                        status="active",
                    )
                    memory_capture(
                        content="Repo A rule",
                        fact_type="rule",
                        scope="project",
                        project="repo-a",
                        evidence_refs=["repo-a"],
                        status="active",
                    )
                    memory_capture(
                        content="Repo B rule",
                        fact_type="rule",
                        scope="project",
                        project="repo-b",
                        evidence_refs=["repo-b"],
                        status="active",
                    )
                    context = memory_context(query="rule", project="repo-a", chat_id="chat-a", budget_tokens=100)

        data = _structured(context)["data"]
        self.assertEqual(data["count"], 1)
        self.assertIn("Repo A rule", data["context"])
        self.assertNotIn("Repo B rule", data["context"])
