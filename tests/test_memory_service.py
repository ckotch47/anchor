from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_memory_repository import SqliteMemoryRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.memory.service import MemoryService
from anchor.application.retrieval.document_chunking import count_tokens


class MemoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tmpdir.name) / "anchor.sqlite3"
        SqliteMigrationRepository(database_path=database_path).apply_pending()
        self.service = MemoryService(SqliteMemoryRepository(database_path=database_path), project="repo-a", budget_tokens=800)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_recall_includes_global_and_current_project_only(self) -> None:
        self.service.capture(
            content="User prefers pytest",
            fact_type="preference",
            scope="global",
            project="repo-a",
            evidence_refs=["global-evidence"],
            status="active",
        )
        self.service.capture(
            content="Project uses pytest",
            fact_type="rule",
            scope="project",
            project="repo-a",
            evidence_refs=["project-evidence"],
            status="active",
        )
        self.service.capture(
            content="Other project uses pytest",
            fact_type="rule",
            scope="project",
            project="repo-b",
            evidence_refs=["other-evidence"],
            status="active",
        )

        result = self.service.recall(query="pytest", project="repo-a")

        self.assertEqual(result.count, 2)
        self.assertEqual({item.fact.project for item in result.results}, {"repo-a"})

    def test_global_promotion_requires_evidence(self) -> None:
        fact = self.service.capture(
            content="Temporary preference",
            fact_type="preference",
            scope="project",
            evidence_refs=[],
        )

        with self.assertRaises(ValueError):
            self.service.promote(fact.id, scope="global")

    def test_terminal_fact_cannot_be_resurrected(self) -> None:
        fact = self.service.capture(
            content="Retired preference",
            fact_type="preference",
            evidence_refs=["evidence"],
        )
        self.service.update_status(fact.id, "deleted")

        with self.assertRaises(ValueError):
            self.service.update_status(fact.id, "active")

    def test_duplicate_capture_merges_evidence_without_new_fact(self) -> None:
        first = self.service.capture(
            content="User prefers pytest",
            fact_type="preference",
            evidence_refs=["evidence-a"],
            status="active",
        )

        second = self.service.capture(
            content=" user prefers pytest ",
            fact_type="preference",
            evidence_refs=["evidence-b"],
            confidence=0.9,
            status="active",
        )

        self.assertEqual(second.id, first.id)
        self.assertEqual(second.evidence_refs, ["evidence-a", "evidence-b"])
        self.assertEqual(second.confidence, 1.0)

    def test_supersedes_id_marks_previous_fact_superseded(self) -> None:
        previous = self.service.capture(
            content="Use SQLite",
            fact_type="decision",
            evidence_refs=["old-evidence"],
            status="active",
        )

        replacement = self.service.capture(
            content="Use SQLite with WAL",
            fact_type="decision",
            evidence_refs=["new-evidence"],
            status="active",
            supersedes_id=previous.id,
        )

        self.assertEqual(self.service.get(previous.id).status, "superseded")
        self.assertEqual(replacement.supersedes_id, previous.id)

    def test_supersedes_id_cannot_cross_project_boundary(self) -> None:
        previous = self.service.capture(
            content="Use SQLite",
            fact_type="decision",
            project="repo-a",
            evidence_refs=["old-evidence"],
            status="active",
        )

        with self.assertRaises(ValueError):
            self.service.capture(
                content="Use PostgreSQL",
                fact_type="decision",
                project="repo-b",
                evidence_refs=["new-evidence"],
                status="active",
                supersedes_id=previous.id,
            )

    def test_default_search_is_current_project_plus_global(self) -> None:
        self.service.capture(
            content="Current project uses SQLite",
            fact_type="rule",
            project="repo-a",
            evidence_refs=["current"],
            status="active",
        )
        self.service.capture(
            content="Other project uses SQLite",
            fact_type="rule",
            project="repo-b",
            evidence_refs=["other"],
            status="active",
        )

        result = self.service.search(query="SQLite")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].fact.project, "repo-a")

    def test_build_context_formats_current_project_memory(self) -> None:
        self.service.capture(
            content="Project uses SQLite",
            fact_type="rule",
            project="repo-a",
            evidence_refs=["current"],
            status="active",
        )

        result = self.service.build_context(query="SQLite", project="repo-a", chat_id="chat-a")

        self.assertEqual(result.count, 1)
        self.assertIn("<anchor_memory>", result.context)
        self.assertIn("Project: repo-a", result.context)
        self.assertIn("[project:repo-a/rule] Project uses SQLite", result.context)
        self.assertIn("</anchor_memory>", result.context)

    def test_build_context_respects_budget(self) -> None:
        self.service.capture(
            content="A very long project memory fact that should be trimmed when the context budget is small",
            fact_type="rule",
            project="repo-a",
            evidence_refs=["current"],
            status="active",
        )

        result = self.service.build_context(query="project", project="repo-a", budget_tokens=8)

        self.assertEqual(result.budget_tokens, 8)
        self.assertLessEqual(len(result.results), 1)
        self.assertLessEqual(count_tokens(result.context), 8)
        self.assertIn("<anchor_memory>", result.context)

    def test_evidence_resolves_live_history_and_hides_deleted_source(self) -> None:
        with sqlite3.connect(self.service._repository._database_path) as connection:
            connection.execute(
                "INSERT INTO documents (id, project, document_type, title, body, source, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("history-1", "repo-a", "history", "decision", "Use SQLite", "test", "", "now", "now"),
            )
            connection.execute(
                "INSERT INTO history_entries (document_id, project, entry_type, actor, payload, correlation_id) VALUES (?, ?, ?, ?, ?, ?)",
                ("history-1", "repo-a", "decision", "user", "Use SQLite", "corr-1"),
            )
            connection.commit()
        fact = self.service.capture(
            content="Use SQLite",
            fact_type="decision",
            evidence_refs=["history-1"],
            status="active",
        )

        live = self.service.evidence(fact.id, project="repo-a")

        self.assertEqual(live.count, 1)
        self.assertEqual(live.evidence[0].record["payload"] if live.evidence[0].record else None, "Use SQLite")
        with sqlite3.connect(self.service._repository._database_path) as connection:
            connection.execute("UPDATE documents SET deleted_at = 'now' WHERE id = ?", ("history-1",))
            connection.commit()

        deleted = self.service.evidence(fact.id, project="repo-a")

        self.assertEqual(deleted.count, 0)
        self.assertFalse(deleted.evidence[0].found)

    def test_scenarios_are_searchable_in_current_project_scope(self) -> None:
        self.service._repository.create_scenario(
            scope="project",
            project="repo-a",
            title="MCP parity rollout",
            summary="Align MCP tools with the CLI contract.",
            fact_ids=[],
            evidence_refs=["history-1"],
        )

        result = self.service.search_scenarios(query="MCP parity", project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].scenario.title, "MCP parity rollout")

    def test_conflicts_are_read_only_groups_for_review(self) -> None:
        self.service.capture(
            content="Use SQLite",
            fact_type="decision",
            evidence_refs=["evidence-a"],
            status="conflicted",
        )
        self.service.capture(
            content="Use PostgreSQL",
            fact_type="decision",
            evidence_refs=["evidence-b"],
            status="conflicted",
        )

        result = self.service.conflicts(project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual({fact.content for fact in result.groups[0].facts}, {"Use SQLite", "Use PostgreSQL"})

    def test_metrics_report_memory_health(self) -> None:
        self.service.capture(
            content="Current decision",
            fact_type="decision",
            evidence_refs=["missing-evidence", "tests:145-passed"],
            status="active",
        )
        self.service.capture(
            content="Conflicted decision",
            fact_type="decision",
            evidence_refs=[],
            status="conflicted",
        )
        self.service._repository.create_scenario(
            scope="project",
            project="repo-a",
            title="A scenario",
            summary="A summarized scenario.",
            fact_ids=[],
            evidence_refs=[],
        )
        self.service._repository.save_checkpoint(
            project="repo-a",
            chat_id=None,
            last_history_updated_at=None,
            processed_count=2,
            status="completed",
        )

        result = self.service.metrics(project="repo-a")

        self.assertEqual(result.facts_by_status["active"], 1)
        self.assertEqual(result.facts_by_status["conflicted"], 1)
        self.assertEqual(result.scenarios_by_status["active"], 1)
        self.assertEqual(result.conflicted_facts, 1)
        self.assertEqual(result.total_evidence_refs, 2)
        self.assertEqual(result.broken_evidence_refs, 1)
        self.assertEqual(result.broken_canonical_evidence_refs, 1)
        self.assertEqual(result.external_evidence_refs, 1)
        self.assertEqual(result.pending_extraction_count, 0)
        self.assertEqual(result.checkpoints["completed"], 1)

    def test_context_includes_matching_scenario_before_facts(self) -> None:
        self.service._repository.create_scenario(
            scope="project",
            project="repo-a",
            title="MCP parity rollout",
            summary="Align MCP tools with the CLI contract.",
            fact_ids=[],
            evidence_refs=["history-1"],
        )

        result = self.service.build_context(query="MCP parity", project="repo-a")

        self.assertEqual(result.scenario_count, 1)
        self.assertIn("MCP parity rollout", result.context)
