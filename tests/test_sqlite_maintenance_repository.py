from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from anchor.adapters.sqlite_maintenance_repository import SqliteMaintenanceRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.application.retrieval.document_chunking import DocumentChunkDraft


class SqliteMaintenanceRepositoryTest(unittest.TestCase):
    def test_rebuild_search_indexes_restores_fts_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            notes_repository = SqliteNotesRepository(database_path=db_path)
            maintenance_repository = SqliteMaintenanceRepository(database_path=db_path)
            note = notes_repository.create(
                title="Maintenance note",
                body="rebuild the index",
                project="repo-a",
                chunks=[
                    DocumentChunkDraft(
                        chunk_index=0,
                        chunk_text="rebuild the index",
                        token_count=3,
                    )
                ],
            )

            with sqlite3.connect(db_path) as connection:
                connection.execute("DELETE FROM document_chunks_fts WHERE document_type = 'note' AND document_id = ?", (note.id,))
                connection.commit()

            self.assertEqual(notes_repository.search("rebuild", limit=10, project="repo-a"), [])

            rebuilt_tables = maintenance_repository.rebuild_search_indexes()

            self.assertIn("document_chunks_fts", rebuilt_tables)
            self.assertGreater(len(notes_repository.search("rebuild", limit=10, project="repo-a")), 0)

    def test_purge_deleted_documents_removes_soft_deleted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            notes_repository = SqliteNotesRepository(database_path=db_path)
            maintenance_repository = SqliteMaintenanceRepository(database_path=db_path)
            note = notes_repository.create(
                title="Cleanup note",
                body="delete me later",
                project="repo-a",
                chunks=[
                    DocumentChunkDraft(
                        chunk_index=0,
                        chunk_text="delete me later",
                        token_count=3,
                    )
                ],
            )

            notes_repository.delete(note.id, project="repo-a")
            purged = maintenance_repository.purge_deleted_documents(project="repo-a")

            with sqlite3.connect(db_path) as connection:
                document_rows = connection.execute(
                    "SELECT COUNT(*) FROM documents WHERE id = ?",
                    (note.id,),
                ).fetchone()[0]

        self.assertEqual(purged, 1)
        self.assertEqual(document_rows, 0)

    def test_checkpoint_wal_returns_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            maintenance_repository = SqliteMaintenanceRepository(database_path=db_path)

            checkpoint = maintenance_repository.checkpoint_wal()

        self.assertIn("busy", checkpoint)
        self.assertIn("log", checkpoint)
        self.assertIn("checkpointed", checkpoint)

    def test_auto_maintain_if_due_rebuilds_and_updates_last_vacuum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            notes_repository = SqliteNotesRepository(database_path=db_path)
            maintenance_repository = SqliteMaintenanceRepository(database_path=db_path)
            note = notes_repository.create(
                title="Maintenance note",
                body="rebuild me",
                project="repo-a",
                chunks=[
                    DocumentChunkDraft(
                        chunk_index=0,
                        chunk_text="rebuild me",
                        token_count=2,
                    )
                ],
            )

            with sqlite3.connect(db_path) as connection:
                connection.execute("DELETE FROM document_chunks_fts WHERE document_type = 'note' AND document_id = ?", (note.id,))
                connection.execute(
                    """
                    INSERT INTO settings (scope, key, value, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(scope, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (
                        "maintenance",
                        "last_vacuum",
                        (datetime.now(UTC) - timedelta(days=8)).isoformat(),
                        "2026-06-13T00:00:00+00:00",
                    ),
                )
                connection.commit()

            self.assertEqual(notes_repository.search("rebuild", limit=10, project="repo-a"), [])

            ran = maintenance_repository.auto_maintain_if_due()

            with sqlite3.connect(db_path) as connection:
                last_vacuum = connection.execute(
                    "SELECT value FROM settings WHERE scope = ? AND key = ?",
                    ("maintenance", "last_vacuum"),
                ).fetchone()[0]

            self.assertTrue(ran)
            self.assertGreater(len(notes_repository.search("rebuild", limit=10, project="repo-a")), 0)
            self.assertNotEqual(last_vacuum, "2026-06-13T00:00:00+00:00")

    def test_auto_maintain_if_due_skips_when_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            maintenance_repository = SqliteMaintenanceRepository(database_path=db_path)

            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO settings (scope, key, value, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(scope, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (
                        "maintenance",
                        "last_vacuum",
                        (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                        "2026-06-13T00:00:00+00:00",
                    ),
                )
                connection.commit()

            ran = maintenance_repository.auto_maintain_if_due()

        self.assertFalse(ran)
