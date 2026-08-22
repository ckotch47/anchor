from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
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


class InvalidScenarioProvider(FakeMemoryProvider):
    def summarize_scenario(self, facts: list[str], evidence_refs: list[str], model: str) -> dict[str, object]:
        return {"title": "", "summary": ""}


class RecordingMemoryProvider(FakeMemoryProvider):
    def __init__(self) -> None:
        self.transcript = ""

    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, object]]:
        self.transcript = text
        return super().extract_facts(text, evidence_refs, model)


class SecretFailingMemoryProvider(FakeMemoryProvider):
    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, object]]:
        raise RuntimeError("provider body echoed token=SUPERSECRET123456")


class OversizedMemoryProvider(FakeMemoryProvider):
    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, object]]:
        del text, evidence_refs, model
        return [
            {
                "fact_type": "preference",
                "content": f"Fact {index}",
                "confidence": 0.9,
                "scope": "project",
            }
            for index in range(3)
        ]


class MemoryExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmpdir.name) / "anchor.sqlite3"
        SqliteMigrationRepository(database_path=self.database_path).apply_pending()
        with closing(sqlite3.connect(self.database_path)) as connection:
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
        self.service.configure_extraction(
            FakeMemoryProvider(),
            model="fake-model",
            external_send_allowed=True,
            external_projects=["repo-a"],
        )

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

    def test_extracted_facts_are_promoted_only_after_scenario_validation(self) -> None:
        self.service.configure_extraction(
            InvalidScenarioProvider(),
            model="fake-model",
            external_send_allowed=True,
            external_projects=["repo-a"],
        )

        with self.assertRaisesRegex(RuntimeError, r"memory extraction failed \(ValueError\)"):
            self.service.extract(project="repo-a", chat_id="chat-a")

        facts = self.service._repository.search(
            "pytest", scope="all", projects=["repo-a"], chat_id=None, fact_type=None, statuses=["candidate"], limit=10
        )
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0][0].status, "candidate")

    def test_retry_does_not_duplicate_scenario_or_facts_and_writes_audit(self) -> None:
        first = self.service.extract(project="repo-a", chat_id="chat-a")
        checkpoint = self.service._repository.get_checkpoint(project="repo-a", chat_id="chat-a")
        self.service._repository.save_checkpoint(
            project="repo-a",
            chat_id="chat-a",
            last_history_updated_at=None,
            processed_count=0,
            status="error",
            last_error="simulated retry",
        )

        second = self.service.extract(project="repo-a", chat_id="chat-a")

        self.assertEqual(first.scenario.id if first.scenario else None, second.scenario.id if second.scenario else None)
        self.assertEqual(checkpoint["status"] if checkpoint else None, "completed")
        with closing(sqlite3.connect(self.database_path)) as connection:
            scenario_count = connection.execute("SELECT COUNT(*) FROM memory_scenarios").fetchone()[0]
            audit_count = connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'external_memory_extraction'"
            ).fetchone()[0]
        self.assertEqual(scenario_count, 1)
        self.assertEqual(audit_count, 2)

    def test_external_send_requires_explicit_opt_in(self) -> None:
        self.service.configure_extraction(FakeMemoryProvider(), model="fake-model", external_send_allowed=False)

        with self.assertRaisesRegex(RuntimeError, "external memory extraction is not allowed"):
            self.service.extract(project="repo-a", chat_id="chat-a")

        checkpoint = self.service._repository.get_checkpoint(project="repo-a", chat_id="chat-a")
        self.assertEqual(checkpoint["status"] if checkpoint else None, "error")

    def test_provider_configuration_without_explicit_scope_is_denied(self) -> None:
        self.service.configure_extraction(FakeMemoryProvider(), model="fake-model")

        with self.assertRaisesRegex(RuntimeError, "external memory extraction is not allowed"):
            self.service.extract(project="repo-a", chat_id="chat-a")

    def test_provider_exception_is_sanitized_in_checkpoint_and_public_error(self) -> None:
        self.service.configure_extraction(
            SecretFailingMemoryProvider(),
            model="fake-model",
            external_send_allowed=True,
            external_projects=["repo-a"],
        )

        with self.assertRaisesRegex(RuntimeError, r"memory extraction failed \(RuntimeError\)") as raised:
            self.service.extract(project="repo-a", chat_id="chat-a")

        checkpoint = self.service._repository.get_checkpoint(project="repo-a", chat_id="chat-a")
        self.assertNotIn("SUPERSECRET123456", str(raised.exception))
        self.assertNotIn("SUPERSECRET123456", str(checkpoint["last_error"] if checkpoint else ""))

    def test_provider_fact_count_is_bounded_before_persistence(self) -> None:
        self.service.configure_extraction(
            OversizedMemoryProvider(),
            model="fake-model",
            external_send_allowed=True,
            external_projects=["repo-a"],
            max_extracted_facts=2,
        )

        with self.assertRaisesRegex(RuntimeError, r"memory extraction failed \(ValueError\)"):
            self.service.extract(project="repo-a", chat_id="chat-a")

        facts = self.service._repository.search(
            "Fact",
            scope="all",
            projects=["repo-a"],
            chat_id=None,
            fact_type=None,
            statuses=["candidate", "active"],
            limit=10,
        )
        self.assertEqual([], facts)

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

    def test_extract_redacts_provider_payload_and_counts_changed_items(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE history_entries SET payload = ? WHERE document_id = 'history-1'",
                ("Email user@example.com and token sk-or-v1-1234567890abcdef",),
            )
            connection.commit()
        provider = RecordingMemoryProvider()
        self.service.configure_extraction(
            provider,
            model="fake-model",
            external_send_allowed=True,
            external_projects=["repo-a"],
        )

        self.service.extract(project="repo-a", chat_id="chat-a")

        self.assertNotIn("user@example.com", provider.transcript)
        self.assertNotIn("sk-or-v1-1234567890abcdef", provider.transcript)
        with closing(sqlite3.connect(self.database_path)) as connection:
            payload = connection.execute(
                "SELECT payload FROM events WHERE event_type = 'external_memory_extraction' ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()[0]
        self.assertIn('"redacted_item_count":1', payload.replace(" ", ""))
