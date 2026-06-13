from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.service import FilesService


class FilesServiceTest(unittest.TestCase):
    def test_index_and_search_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            (root / "app.py").write_text(
                "def greet():\n    return 'hello world'\n\nclass Greeter:\n    pass\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text("# Deploy\n\nUse hello world in docs.\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.py").write_text("print('ignore')", encoding="utf-8")

            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            service = FilesService(
                repository=SqliteFilesRepository(database_path=db_path),
                chunking_service=FileChunkingService(),
                project="repo-a",
                roots=[str(root)],
                ignore_patterns=["node_modules/"],
                chunk_size=40,
                chunk_overlap=10,
            )

            indexed = service.index(project="repo-a")
            result = service.search("greet", project="repo-a")

        self.assertEqual(indexed.indexed, 2)
        self.assertGreaterEqual(indexed.skipped, 1)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].file.path, str((root / "app.py").resolve()))

    def test_index_removes_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            file_path = root / "app.py"
            file_path.write_text("print('hello')\n", encoding="utf-8")

            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            service = FilesService(
                repository=SqliteFilesRepository(database_path=db_path),
                chunking_service=FileChunkingService(),
                project="repo-a",
                roots=[str(root)],
                chunk_size=40,
                chunk_overlap=10,
            )

            service.index(project="repo-a")
            file_path.unlink()
            indexed = service.index(project="repo-a")
            result = service.search("hello", project="repo-a")

        self.assertGreaterEqual(indexed.deleted, 1)
        self.assertEqual(result.count, 0)
