from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.files.chunking import FileChunkDraft


class SqliteFilesRepositoryTest(unittest.TestCase):
    def test_list_and_search_apply_sql_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            repository = SqliteFilesRepository(database_path=db_path)

            repository.upsert_file(
                document_id=uuid7_str(),
                project="repo-a",
                path="/repo/src/app.py",
                root_path="/repo",
                language="python",
                metatags={},
                file_size=42,
                content_hash="hash-1",
                mtime_ns=1,
                chunks=[
                    FileChunkDraft(
                        chunk_index=0,
                        chunk_text="deploy hello",
                        token_count=2,
                        start_line=1,
                        end_line=1,
                    )
                ],
            )
            repository.upsert_file(
                document_id=uuid7_str(),
                project="repo-a",
                path="/repo/docs/readme.md",
                root_path="/repo",
                language="markdown",
                metatags={},
                file_size=24,
                content_hash="hash-2",
                mtime_ns=2,
                chunks=[
                    FileChunkDraft(
                        chunk_index=0,
                        chunk_text="deploy hello",
                        token_count=2,
                        start_line=1,
                        end_line=1,
                    )
                ],
            )

            files = repository.list_indexed_files(
                project="repo-a",
                root_path="/repo",
                language="python",
                path_prefix="/repo/src",
                limit=10,
            )
            lexical_candidates = repository.search_lexical_candidates(
                query="deploy",
                limit=10,
                project="repo-a",
                root_path="/repo",
                language="python",
                path_prefix="/repo/src",
            )

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "/repo/src/app.py")
        self.assertEqual(len(lexical_candidates), 1)
        self.assertEqual(lexical_candidates[0].file.path, "/repo/src/app.py")

    def test_delete_removes_file_from_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            repository = SqliteFilesRepository(database_path=db_path)
            document_id = uuid7_str()

            repository.upsert_file(
                document_id=document_id,
                project="repo-a",
                path="/repo/src/app.py",
                root_path="/repo",
                language="python",
                metatags={},
                file_size=42,
                content_hash="hash-1",
                mtime_ns=1,
                chunks=[
                    FileChunkDraft(
                        chunk_index=0,
                        chunk_text="deploy hello",
                        token_count=2,
                        start_line=1,
                        end_line=1,
                    )
                ],
            )

            deleted = repository.delete(document_id, project="repo-a")
            files = repository.list_indexed_files(project="repo-a", limit=10)
            lexical_candidates = repository.search_lexical_candidates(query="deploy", limit=10, project="repo-a")
            record = repository.get(document_id, project="repo-a")

        self.assertIsNotNone(deleted)
        self.assertEqual(deleted.path, "/repo/src/app.py")
        self.assertEqual(files, [])
        self.assertEqual(lexical_candidates, [])
        self.assertIsNone(record)
