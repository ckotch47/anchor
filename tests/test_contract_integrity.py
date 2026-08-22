from __future__ import annotations

import inspect
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from anchor import __version__
from anchor.adapters.sqlite_links_repository import SqliteLinksRepository
from anchor.adapters.sqlite_memory_repository import SqliteMemoryRepository
from anchor.adapters.sqlite_migration_repository import (
    MIGRATIONS,
    Migration,
    SqliteMigrationRepository,
)
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.links.service import DocumentLinksService
from anchor.application.memory.service import MemoryService
from anchor.application.tasks.service import TasksService
from anchor.cli import capabilities_command
from anchor.cli_tasks import tasks_update as cli_tasks_update
from anchor.cli_tasks import tasks_upsert as cli_tasks_upsert
from anchor.mcp_server import tasks_update as mcp_tasks_update
from anchor.mcp_server import tasks_upsert as mcp_tasks_upsert


class ContractIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmpdir.name) / "anchor.sqlite3"
        result = SqliteMigrationRepository(database_path=self.database_path).apply_pending()
        self.assertEqual(result.current_version, 13)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_links_fail_closed_across_projects(self) -> None:
        notes = SqliteNotesRepository(database_path=self.database_path)
        source = notes.create(title="A", body="A", project="repo-a")
        target = notes.create(title="B", body="B", project="repo-b")
        service = DocumentLinksService(SqliteLinksRepository(database_path=self.database_path))

        with self.assertRaises(LookupError):
            service.create("repo-a", source.id, target.id, "references")
        self.assertEqual(service.list_by_source(source.id, project="repo-a").count, 0)
        with self.assertRaises(LookupError):
            service.delete("repo-a", source.id, target.id, "references")

    def test_memory_mutations_require_source_project(self) -> None:
        service = MemoryService(SqliteMemoryRepository(database_path=self.database_path), project="repo-a")
        fact = service.capture(
            content="validated fact", fact_type="rule", project="repo-a", evidence_refs=["external:evidence"]
        )

        with self.assertRaises(LookupError):
            service.update_status(fact.id, "active", project="repo-b")
        promoted = service.promote(fact.id, scope="global", source_project="repo-a")
        self.assertEqual(promoted.scope, "global")
        self.assertEqual(promoted.project, "repo-a")
        self.assertEqual(promoted.status, "active")

    def test_task_relations_lifecycle_and_exact_upsert(self) -> None:
        service = TasksService(SqliteTasksRepository(database_path=self.database_path), project="repo-a")
        parent = service.add(title="Parent")
        foreign = TasksService(SqliteTasksRepository(database_path=self.database_path), project="repo-b").add(title="Foreign")

        with self.assertRaises(LookupError):
            service.add(title="Invalid", parent_document_id=foreign.id)
        child = service.add(title="Child", parent_document_id=parent.id)
        with self.assertRaisesRegex(ValueError, "parent_document_id would create a cycle"):
            service.update(parent.id, parent_document_id=child.id)
        blocker = service.add(title="Blocker", blocked_by_document_id=child.id)
        with self.assertRaisesRegex(ValueError, "blocked_by_document_id would create a cycle"):
            service.update(child.id, blocked_by_document_id=blocker.id)
        blocked = service.set_status(child.id, status="blocked", blocked_reason="waiting")
        self.assertEqual(blocked.status, "blocked")
        done = service.done(child.id)
        closed = service.set_status(done.id, status="closed")
        self.assertEqual(closed.status, "closed")
        with self.assertRaises(ValueError):
            service.set_status(closed.id, status="in_progress")

        first = service.upsert(
            external_key="work-42",
            title="First",
            source_ref="legacy-ref",
            due_at="2026-09-01T00:00:00Z",
            parent_document_id=parent.id,
            blocked_by_document_id=blocker.id,
        )
        second = service.upsert(external_key="work-42", title="Second", source_ref="legacy-ref-2")
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.title, "Second")
        self.assertEqual(second.external_key, "work-42")
        self.assertEqual(second.source_ref, "legacy-ref-2")
        self.assertIsNone(second.due_at)
        self.assertIsNone(second.parent_document_id)
        self.assertIsNone(second.blocked_by_document_id)

    def test_capabilities_cli_has_stable_scoped_contract(self) -> None:
        with patch("typer.echo") as echo_mock:
            capabilities_command(format="json")
        payload = json.loads(echo_mock.call_args.args[0])
        data = payload["data"]
        self.assertEqual(data["contract_version"], "1.0")
        self.assertEqual(data["surfaces"]["links"]["add"]["scope"], "project_required")
        parameters = data["surfaces"]["memory"]["status"]["parameters"]
        self.assertIn({"name": "project", "required": True, "type": "string"}, parameters)

    def test_ordinary_cli_does_not_eagerly_import_optional_mcp_stack(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "anchor", "--version"],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"anchor v{__version__}")
        self.assertEqual(result.stderr, "")

    def test_task_upsert_capability_matches_both_transport_parameters(self) -> None:
        with patch("typer.echo") as echo_mock:
            capabilities_command(format="json")
        payload = json.loads(echo_mock.call_args.args[0])
        declared = {
            parameter["name"]
            for parameter in payload["data"]["surfaces"]["tasks"]["upsert"]["parameters"]
        }
        public_parameters = {
            "external_key",
            "title",
            "project",
            "body",
            "source",
            "source_ref",
            "priority",
            "due_at",
            "task_kind",
            "parent_document_id",
            "blocked_by_document_id",
            "metatags",
        }
        self.assertEqual(declared, public_parameters)
        self.assertTrue(public_parameters.issubset(inspect.signature(cli_tasks_upsert).parameters))
        self.assertTrue(public_parameters.issubset(inspect.signature(mcp_tasks_upsert).parameters))
        self.assertEqual(inspect.signature(cli_tasks_upsert).parameters["source"].default, "anchor")
        self.assertEqual(inspect.signature(mcp_tasks_upsert).parameters["source"].default, "anchor")

    def test_task_update_clear_contract_matches_both_transports(self) -> None:
        with patch("typer.echo") as echo_mock:
            capabilities_command(format="json")
        payload = json.loads(echo_mock.call_args.args[0])
        declared = {
            parameter["name"]
            for parameter in payload["data"]["surfaces"]["tasks"]["update"]["parameters"]
        }
        clear_parameters = {
            "clear_due_at",
            "clear_parent_document_id",
            "clear_blocked_by_document_id",
        }

        self.assertTrue(clear_parameters.issubset(declared))
        self.assertTrue(clear_parameters.issubset(inspect.signature(cli_tasks_update).parameters))
        self.assertTrue(clear_parameters.issubset(inspect.signature(mcp_tasks_update).parameters))

    def test_external_key_migration_preserves_legacy_source_ref(self) -> None:
        legacy_path = Path(self.tmpdir.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            for migration in MIGRATIONS[:11]:
                connection.executescript(migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?, 'applied')",
                    (migration.version, migration.name, migration.checksum, utc_now_iso()),
                )
            task_id = "01a01e79-9537-7738-9bd3-c43e89f724e3"
            now = utc_now_iso()
            connection.execute(
                """
                INSERT INTO documents
                    (id, project, metatags, correlation_id, document_type, title, body,
                     source, source_ref, created_at, updated_at, deleted_at)
                VALUES (?, 'repo-a', '{}', '', 'task', 'Legacy', 'Legacy',
                        'integration', 'legacy-ref', ?, ?, NULL)
                """,
                (task_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO tasks
                    (document_id, project, metatags, task_kind, status, priority, due_at,
                     started_at, completed_at, blocked_reason, parent_document_id,
                     blocked_by_document_id)
                VALUES (?, 'repo-a', '{}', 'task', 'open', 0, NULL, NULL, NULL, NULL, NULL, NULL)
                """,
                (task_id,),
            )
            orchestration_id = "01a01e79-9537-7738-9bd3-c43e89f724e4"
            connection.execute(
                """
                INSERT INTO documents
                    (id, project, metatags, correlation_id, document_type, title, body,
                     source, source_ref, created_at, updated_at, deleted_at)
                VALUES (?, 'repo-a', '{}', '', 'task', 'Orchestrated', 'Orchestrated',
                        'myskills-orchestration', 'orchestration:key-1', ?, ?, NULL)
                """,
                (orchestration_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO tasks
                    (document_id, project, metatags, task_kind, status, priority, due_at,
                     started_at, completed_at, blocked_reason, parent_document_id,
                     blocked_by_document_id)
                VALUES (?, 'repo-a', '{}', 'task', 'open', 0, NULL, NULL, NULL, NULL, NULL, NULL)
                """,
                (orchestration_id,),
            )
            for index, deleted_at in enumerate((None, now), start=1):
                duplicate_id = f"01a01e79-9537-7738-9bd3-c43e89f724e{4 + index}"
                connection.execute(
                    """
                    INSERT INTO documents
                        (id, project, metatags, correlation_id, document_type, title, body,
                         source, source_ref, created_at, updated_at, deleted_at)
                    VALUES (?, 'repo-a', '{}', '', 'task', 'Duplicate', 'Duplicate',
                            'myskills-orchestration', 'orchestration:duplicate', ?, ?, ?)
                    """,
                    (duplicate_id, now, now, deleted_at),
                )
                connection.execute(
                    """
                    INSERT INTO tasks
                        (document_id, project, metatags, task_kind, status, priority, due_at,
                         started_at, completed_at, blocked_reason, parent_document_id,
                         blocked_by_document_id)
                    VALUES (?, 'repo-a', '{}', 'task', 'open', 0, NULL, NULL, NULL, NULL, NULL, NULL)
                    """,
                    (duplicate_id,),
                )
            foreign_id = "01a01e79-9537-7738-9bd3-c43e89f724e7"
            connection.execute(
                """
                INSERT INTO documents
                    (id, project, metatags, correlation_id, document_type, title, body,
                     source, source_ref, created_at, updated_at, deleted_at)
                VALUES (?, 'repo-b', '{}', '', 'task', 'Foreign', 'Foreign',
                        'test', '', ?, ?, NULL)
                """,
                (foreign_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO tasks
                    (document_id, project, metatags, task_kind, status, priority, due_at,
                     started_at, completed_at, blocked_reason, parent_document_id,
                     blocked_by_document_id)
                VALUES (?, 'repo-b', '{}', 'task', 'open', 0, NULL, NULL, NULL, NULL, NULL, NULL)
                """,
                (foreign_id,),
            )
            note_id = "01a01e79-9537-7738-9bd3-c43e89f724e8"
            connection.execute(
                """
                INSERT INTO documents
                    (id, project, metatags, correlation_id, document_type, title, body,
                     source, source_ref, created_at, updated_at, deleted_at)
                VALUES (?, 'repo-a', '{}', '', 'note', 'Not a task', 'Not a task',
                        'test', '', ?, ?, NULL)
                """,
                (note_id, now, now),
            )
            connection.execute(
                "INSERT INTO notes(document_id, project, metatags) VALUES (?, 'repo-a', '{}')",
                (note_id,),
            )
            connection.execute(
                """
                UPDATE tasks
                SET parent_document_id = ?, blocked_by_document_id = ?
                WHERE document_id = ? AND project = 'repo-a'
                """,
                (foreign_id, note_id, orchestration_id),
            )
            connection.commit()

        result = SqliteMigrationRepository(database_path=legacy_path).apply_pending()
        self.assertEqual(result.applied_versions[-1], 13)
        task = SqliteTasksRepository(database_path=legacy_path).get(task_id, project="repo-a")
        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.source_ref, "legacy-ref")
        self.assertIsNone(task.external_key)
        orchestrated = SqliteTasksRepository(database_path=legacy_path).get(
            orchestration_id, project="repo-a"
        )
        self.assertIsNotNone(orchestrated)
        assert orchestrated is not None
        self.assertEqual(orchestrated.external_key, "orchestration:key-1")
        self.assertIsNone(orchestrated.parent_document_id)
        self.assertIsNone(orchestrated.blocked_by_document_id)
        with closing(sqlite3.connect(legacy_path)) as connection:
            duplicate_keys = connection.execute(
                """
                SELECT t.external_key
                FROM tasks AS t
                JOIN documents AS d ON d.id = t.document_id
                WHERE d.source_ref = 'orchestration:duplicate'
                ORDER BY d.id
                """
            ).fetchall()
            quarantined = connection.execute(
                """
                SELECT COUNT(*) FROM task_external_key_quarantine
                WHERE project = 'repo-a'
                  AND external_key = 'orchestration:duplicate'
                  AND reason = 'duplicate_legacy_myskills_identity'
                """
            ).fetchone()[0]
            relation_quarantine = connection.execute(
                """
                SELECT COUNT(*) FROM task_relation_quarantine
                WHERE task_document_id = ? AND task_project = 'repo-a'
                  AND reason = 'cross_project_or_deleted_endpoint'
                """,
                (orchestration_id,),
            ).fetchone()[0]
        self.assertEqual(duplicate_keys, [(None,), (None,)])
        self.assertEqual(quarantined, 1)
        self.assertEqual(relation_quarantine, 2)

    def test_migration_failure_rolls_back_schema_and_retries_cleanly(self) -> None:
        legacy_path = Path(self.tmpdir.name) / "retry.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            for migration in MIGRATIONS[:11]:
                connection.executescript(migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?, 'applied')",
                    (migration.version, migration.name, migration.checksum, utc_now_iso()),
                )
            connection.commit()

        repository = SqliteMigrationRepository(database_path=legacy_path)
        original_record = repository._record_migration

        def fail_version_twelve(
            connection: sqlite3.Connection, migration: Migration
        ) -> None:
            if migration.version == 12:
                raise RuntimeError("simulated migration ledger failure")
            original_record(connection, migration)

        with patch.object(
            repository, "_record_migration", side_effect=fail_version_twelve
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated migration ledger failure"):
                repository.apply_pending()

        with closing(sqlite3.connect(legacy_path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(tasks)")
            }
            version = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        self.assertNotIn("external_key", columns)
        self.assertEqual(version, 11)

        result = repository.apply_pending()
        self.assertEqual(result.current_version, 13)
        self.assertIn(12, result.applied_versions)

    def test_v13_quarantine_failure_rolls_back_and_retries_cleanly(self) -> None:
        legacy_path = Path(self.tmpdir.name) / "retry-v13.sqlite3"
        repository = SqliteMigrationRepository(database_path=legacy_path)
        with patch("anchor.adapters.sqlite_migration_repository.MIGRATIONS", MIGRATIONS[:12]):
            repository.apply_pending()

        source = SqliteNotesRepository(database_path=legacy_path).create(
            title="Source", body="Source", project="repo-a"
        )
        foreign_note = SqliteNotesRepository(database_path=legacy_path).create(
            title="Foreign", body="Foreign", project="repo-b"
        )
        task = SqliteTasksRepository(database_path=legacy_path).create(
            title="Task", body="Task", project="repo-a"
        )
        foreign_task = SqliteTasksRepository(database_path=legacy_path).create(
            title="Foreign task", body="Foreign task", project="repo-b"
        )
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute(
                "INSERT INTO document_links VALUES (?, ?, 'references', ?)",
                (source.id, foreign_note.id, utc_now_iso()),
            )
            connection.execute(
                "UPDATE tasks SET parent_document_id = ? WHERE document_id = ?",
                (foreign_task.id, task.id),
            )
            connection.commit()

        original_record = repository._record_migration

        def fail_version_thirteen(connection: sqlite3.Connection, migration: Migration) -> None:
            if migration.version == 13:
                raise RuntimeError("simulated v13 ledger failure")
            original_record(connection, migration)

        with patch.object(repository, "_record_migration", side_effect=fail_version_thirteen):
            with self.assertRaisesRegex(RuntimeError, "simulated v13 ledger failure"):
                repository.apply_pending()

        with closing(sqlite3.connect(legacy_path)) as connection:
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            link_count = connection.execute("SELECT COUNT(*) FROM document_links").fetchone()[0]
            parent_id = connection.execute(
                "SELECT parent_document_id FROM tasks WHERE document_id = ?", (task.id,)
            ).fetchone()[0]
            quarantine_tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)",
                ("document_link_quarantine", "task_relation_quarantine"),
            ).fetchone()[0]
        self.assertEqual(version, 12)
        self.assertEqual(link_count, 1)
        self.assertEqual(parent_id, foreign_task.id)
        self.assertEqual(quarantine_tables, 0)

        result = repository.apply_pending()
        self.assertEqual(result.current_version, 13)
        with closing(sqlite3.connect(legacy_path)) as connection:
            link_count = connection.execute("SELECT COUNT(*) FROM document_links").fetchone()[0]
            parent_id = connection.execute(
                "SELECT parent_document_id FROM tasks WHERE document_id = ?", (task.id,)
            ).fetchone()[0]
            link_quarantine = connection.execute("SELECT COUNT(*) FROM document_link_quarantine").fetchone()[0]
            relation_quarantine = connection.execute("SELECT COUNT(*) FROM task_relation_quarantine").fetchone()[0]
        self.assertEqual(link_count, 0)
        self.assertIsNone(parent_id)
        self.assertEqual(link_quarantine, 1)
        self.assertEqual(relation_quarantine, 1)


if __name__ == "__main__":
    unittest.main()
