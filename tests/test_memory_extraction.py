from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_memory_repository import SqliteMemoryRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.memory.service import MemoryService


class FakeMemoryProvider:
    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, object]]:
        assert text and evidence_refs and model
        return [{"fact_type": "preference", "content": "User prefers pytest", "confidence": 0.95, "scope": "global"}]

    def summarize_scenario(self, facts: list[str], evidence_refs: list[str], model: str) -> dict[str, object]:
        assert facts and evidence_refs and model
        return {"title": "Testing preferences", "summary": "The user prefers pytest."}


class MemoryExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmpdir.name) / "anchor.sqlite3"
        SqliteMigrationRepository(database_path=self.database_path).apply_pending()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO documents (id, project, document_type, title, body, source, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("history-1", "repo-a", "history", "chat", "User prefers pytest", "test", "", "2026-01-01", "2026-01-01"),
            )
            connection.execute(
                "INSERT INTO history_entries (document_id, project, entry_type, actor, payload, correlation_id) VALUES (?, ?, ?, ?, ?, ?)",
                ("history-1", "repo-a", "conversation", "user", "User prefers pytest", "corr-1"),
            )
            connection.commit()
        self.service = MemoryService(SqliteMemoryRepository(database_path=self.database_path), project="repo-a")
        self.service.configure_extraction(FakeMemoryProvider(), model="fake-model")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_extract_creates_fact_scenario_and_checkpoint(self) -> None:
        result = self.service.extract(project="repo-a", chat_id="chat-a")

        self.assertEqual(result.processed_history, 1)
        self.assertEqual(result.extracted_facts, 1)
        self.assertIsNotNone(result.scenario)
        self.assertEqual(result.checkpoint_status, "completed")

        second = self.service.extract(project="repo-a", chat_id="chat-a")
        self.assertEqual(second.processed_history, 0)

    def test_external_send_requires_explicit_opt_in(self) -> None:
        self.service.configure_extraction(FakeMemoryProvider(), model="fake-model", external_send_allowed=False)

        with self.assertRaisesRegex(RuntimeError, "external memory extraction is not allowed"):
            self.service.extract(project="repo-a", chat_id="chat-a")

        checkpoint = self.service._repository.get_checkpoint(project="repo-a", chat_id="chat-a")
        self.assertEqual(checkpoint["status"] if checkpoint else None, "error")

    def test_preview_is_redacted_and_does_not_call_provider(self) -> None:
        self.service.configure_extraction(FakeMemoryProvider(), model="fake-model", external_send_allowed=False)
        preview = self.service.preview_extraction(project="repo-a")

        self.assertFalse(preview["allowed"])
        self.assertEqual(preview["count"], 1)
        self.assertEqual(preview["entries"][0]["payload"], "User prefers pytest")

    def test_preview_supports_explicit_all_projects_wildcard(self) -> None:
        self.service.configure_extraction(
            FakeMemoryProvider(),
            model="fake-model",
            external_send_allowed=True,
            external_projects=["*"],
        )

        preview = self.service.preview_extraction(project="repo-a")

        self.assertTrue(preview["allowed"])
