from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_memory_repository import (
    SqliteMemoryRepository,
    invalidate_memory_facts_for_evidence,
)
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.memory.models import MemoryFactCreate


class SqliteMemoryRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmpdir.name) / "anchor.sqlite3"
        SqliteMigrationRepository(database_path=self.database_path).apply_pending()
        self.repository = SqliteMemoryRepository(database_path=self.database_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_create_round_trips_fact_and_evidence(self) -> None:
        fact = self.repository.create(
            MemoryFactCreate(
                scope="global",
                project="repo-a",
                source_chat_id="chat-1",
                fact_type="preference",
                content="User prefers pytest",
                confidence=0.9,
                evidence_refs=["document-1", {"id": "chunk-1", "type": "chunk"}],
            )
        )

        loaded = self.repository.get(fact.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.evidence_refs if loaded else [], fact.evidence_refs)
        self.assertEqual(fact.scope, "global")

    def test_find_duplicate_is_scoped_and_merges_evidence(self) -> None:
        fact = self.repository.create(
            MemoryFactCreate(
                scope="project",
                project="repo-a",
                fact_type="rule",
                content="Use SQLite",
                confidence=0.5,
                status="active",
                evidence_refs=["evidence-a"],
            )
        )
        duplicate = self.repository.find_duplicate(
            MemoryFactCreate(
                scope="project",
                project="repo-a",
                fact_type="rule",
                content=" use sqlite ",
                confidence=0.9,
                status="active",
                evidence_refs=["evidence-b"],
            )
        )

        self.assertEqual(duplicate.id if duplicate else None, fact.id)
        merged = self.repository.merge_duplicate(
            fact.id,
            evidence_refs=["evidence-b"],
            confidence=0.9,
            status="active",
        )
        self.assertEqual(merged.evidence_refs if merged else [], ["evidence-a", "evidence-b"])

    def test_search_filters_global_project_and_chat_for_recall(self) -> None:
        self.repository.create(
            MemoryFactCreate(
                scope="global",
                project="repo-a",
                source_chat_id="chat-a",
                fact_type="preference",
                content="User prefers pytest globally",
                confidence=1.0,
                status="active",
                evidence_refs=["e-global"],
            )
        )
        self.repository.create(
            MemoryFactCreate(
                scope="project",
                project="repo-a",
                source_chat_id="chat-a",
                fact_type="rule",
                content="Project uses pytest for tests",
                confidence=1.0,
                status="active",
                evidence_refs=["e-project"],
            )
        )
        self.repository.create(
            MemoryFactCreate(
                scope="project",
                project="repo-b",
                source_chat_id="chat-b",
                fact_type="rule",
                content="Other project uses pytest",
                confidence=1.0,
                status="active",
                evidence_refs=["e-other"],
            )
        )

        hits = self.repository.search("pytest", scope="all", projects=["repo-a"], chat_id="chat-a")

        self.assertEqual(len(hits), 2)
        self.assertEqual({hit[0].project for hit in hits}, {"repo-a"})

    def test_invalidate_by_evidence_marks_fact_deleted(self) -> None:
        fact = self.repository.create(
            MemoryFactCreate(
                scope="project",
                project="repo-a",
                fact_type="decision",
                content="Use SQLite",
                confidence=1.0,
                status="active",
                evidence_refs=["document-1"],
            )
        )

        self.assertEqual(self.repository.invalidate_by_evidence(["document-1"]), 1)
        deleted = self.repository.get(fact.id)
        self.assertIsNotNone(deleted)
        self.assertEqual(deleted.status if deleted else None, "deleted")

    def test_document_deletion_helper_also_invalidates_chunk_evidence(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO documents (id, project, document_type, title, body, source, source_ref, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("document-1", "repo-a", "history", "History", "body", "test", "", "now", "now"),
            )
            connection.execute(
                "INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, token_count, created_at, project, metatags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("chunk-1", "document-1", 0, "body", 1, "now", "repo-a", "{}"),
            )
            connection.commit()
        fact = self.repository.create(
            MemoryFactCreate(
                scope="project",
                project="repo-a",
                fact_type="decision",
                content="Derived from a chunk",
                confidence=1.0,
                status="active",
                evidence_refs=["chunk-1"],
            )
        )

        self.assertEqual(invalidate_memory_facts_for_evidence(self.database_path, ["document-1"]), 1)
        self.assertEqual(self.repository.get(fact.id).status, "deleted")
