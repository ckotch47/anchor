from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.embeddings.models import ChunkEmbeddingRecord
from anchor.application.embeddings.service import ChunkEmbeddingsResult
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.models import FileListItem, FileSearchCandidate, IndexedFileRecord
from anchor.application.files.service import FilesService

FILE_ID = uuid7_str()
FILE_CHUNK_ID = uuid7_str()
FILE_EMBEDDING_CHUNK_ID = uuid7_str()


class FilesServiceTest(unittest.TestCase):
    def test_get_returns_full_record_by_id(self) -> None:
        class FakeRepository:
            def get(self, document_id: str, *, project: str):
                del project
                if document_id != FILE_ID:
                    return None
                return IndexedFileRecord(
                    id=FILE_ID,
                    project="repo-a",
                    metatags={},
                    path="/repo/app.py",
                    root_path="/repo",
                    language="python",
                    file_size=42,
                    content_hash="hash",
                    mtime_ns=1,
                    created_at="2026-06-13T00:00:00+00:00",
                    updated_at="2026-06-13T00:00:00+00:00",
                    deleted_at=None,
                )

            def get_by_path(self, *, project: str, path: str):
                del project, path
                return None

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.get(file_id=FILE_ID, project="repo-a")

        self.assertEqual(result.file.id, FILE_ID)
        self.assertEqual(result.file.path, "/repo/app.py")

    def test_get_returns_full_record_by_path(self) -> None:
        class FakeRepository:
            def get(self, document_id: str, *, project: str):
                del document_id, project
                return None

            def get_by_path(self, *, project: str, path: str):
                del project
                if path != "/repo/app.py":
                    return None
                return IndexedFileRecord(
                    id=FILE_ID,
                    project="repo-a",
                    metatags={},
                    path="/repo/app.py",
                    root_path="/repo",
                    language="python",
                    file_size=42,
                    content_hash="hash",
                    mtime_ns=1,
                    created_at="2026-06-13T00:00:00+00:00",
                    updated_at="2026-06-13T00:00:00+00:00",
                    deleted_at=None,
                )

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.get(path="/repo/app.py", project="repo-a")

        self.assertEqual(result.file.id, FILE_ID)
        self.assertEqual(result.file.path, "/repo/app.py")

    def test_get_normalizes_relative_path_against_root(self) -> None:
        class FakeRepository:
            def get(self, document_id: str, *, project: str):
                del document_id, project
                return None

            def get_by_path(self, *, project: str, path: str):
                del project
                if path != "/repo/app.py":
                    return None
                return IndexedFileRecord(
                    id=FILE_ID,
                    project="repo-a",
                    metatags={},
                    path="/repo/app.py",
                    root_path="/repo",
                    language="python",
                    file_size=42,
                    content_hash="hash",
                    mtime_ns=1,
                    created_at="2026-06-13T00:00:00+00:00",
                    updated_at="2026-06-13T00:00:00+00:00",
                    deleted_at=None,
                )

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.get(path="app.py", root="/repo", project="repo-a")

        self.assertEqual(result.file.path, "/repo/app.py")

    def test_delete_normalizes_relative_path_against_root(self) -> None:
        class FakeRepository:
            def get(self, document_id: str, *, project: str):
                del document_id, project
                return None

            def get_by_path(self, *, project: str, path: str):
                del project
                if path != "/repo/app.py":
                    return None
                return IndexedFileRecord(
                    id=FILE_ID,
                    project="repo-a",
                    metatags={},
                    path="/repo/app.py",
                    root_path="/repo",
                    language="python",
                    file_size=42,
                    content_hash="hash",
                    mtime_ns=1,
                    created_at="2026-06-13T00:00:00+00:00",
                    updated_at="2026-06-13T00:00:00+00:00",
                    deleted_at=None,
                )

            def delete(self, document_id: str, *, project: str):
                del project
                if document_id != FILE_ID:
                    return None
                return IndexedFileRecord(
                    id=FILE_ID,
                    project="repo-a",
                    metatags={},
                    path="/repo/app.py",
                    root_path="/repo",
                    language="python",
                    file_size=42,
                    content_hash="hash",
                    mtime_ns=1,
                    created_at="2026-06-13T00:00:00+00:00",
                    updated_at="2026-06-13T00:00:00+00:00",
                    deleted_at="2026-06-13T00:00:00+00:00",
                )

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.delete(path="app.py", root="/repo", project="repo-a")

        self.assertEqual(result.file.path, "/repo/app.py")

    def test_list_returns_compact_file_items(self) -> None:
        class FakeRepository:
            def list_indexed_files(self, *, project: str, root_path: str | None = None, language: str | None = None, path_prefix: str | None = None, limit: int | None = None):
                del project, root_path, language, path_prefix, limit
                return [
                    FileListItem(
                        id=FILE_ID,
                        path="/repo/app.py",
                        root_path="/repo",
                        language="python",
                        file_size=42,
                    )
                ]

        service = FilesService(
            repository=FakeRepository(),
            chunking_service=FileChunkingService(),
            project="repo-a",
        )

        result = service.list(project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.files[0].id, FILE_ID)
        self.assertEqual(result.files[0].path, "/repo/app.py")

    def test_list_applies_filters(self) -> None:
        class FakeRepository:
            def list_indexed_files(
                self,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
                limit: int | None = None,
            ):
                del project, limit
                if root_path == "/repo" and language == "python" and path_prefix == "/repo/app":
                    return [
                        FileListItem(
                            id=FILE_ID,
                            path="/repo/app.py",
                            root_path="/repo",
                            language="python",
                            file_size=42,
                        )
                    ]
                return [
                    FileListItem(
                        id=uuid7_str(),
                        path="/repo/app.md",
                        root_path="/repo",
                        language="markdown",
                        file_size=24,
                    )
                ]

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.list(project="repo-a", root="/repo", language="python", path_prefix="app")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.files[0].language, "python")
        self.assertEqual(result.files[0].path, "/repo/app.py")

    def test_search_uses_vector_and_rerank(self) -> None:
        class FakeRepository:
            def search_lexical_candidates(
                self,
                query: str,
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query, limit, project, root_path, language, path_prefix
                return [
                    FileSearchCandidate(
                        file=FileListItem(
                            id=FILE_ID,
                            path="/repo/app.py",
                            root_path="/repo",
                            language="python",
                            file_size=42,
                        ),
                        chunk_id=FILE_CHUNK_ID,
                        snippet="lexical snippet",
                        token_count=2,
                        lexical_score=0.2,
                    )
                ]

            def search_vector_candidates(
                self,
                query_embedding: list[float],
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query_embedding, limit, project, root_path, language, path_prefix
                return [
                    FileSearchCandidate(
                        file=FileListItem(
                            id=FILE_ID,
                            path="/repo/app.py",
                            root_path="/repo",
                            language="python",
                            file_size=42,
                        ),
                        chunk_id=FILE_CHUNK_ID,
                        snippet="vector snippet with more detail",
                        token_count=4,
                        vector_score=0.9,
                    )
                ]

        class FakeEmbeddingService:
            def embed_texts(self, texts: list[str]) -> ChunkEmbeddingsResult:
                del texts
                return ChunkEmbeddingsResult(
                    model="fake",
                    embeddings=[ChunkEmbeddingRecord(chunk_id=FILE_EMBEDDING_CHUNK_ID, model="fake", embedding=[1.0, 0.0])],
                )

        class FakeRerankService:
            def rerank(self, query: str, texts: list[str]) -> list[float]:
                del query, texts
                return [0.95]

        service = FilesService(
            repository=FakeRepository(),
            chunking_service=FileChunkingService(),
            project="repo-a",
            embedding_service=FakeEmbeddingService(),
            rerank_service=FakeRerankService(),
        )

        result = service.search("deploy", project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].file.id, FILE_ID)
        self.assertGreater(result.results[0].score, 0.7)
        self.assertEqual(result.results[0].snippet, "vector snippet with more detail")

    def test_search_explain_returns_stats(self) -> None:
        class FakeRepository:
            def search_lexical_candidates(
                self,
                query: str,
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query, limit, project, root_path, language, path_prefix
                return [
                    FileSearchCandidate(
                        file=FileListItem(
                            id=FILE_ID,
                            path="/repo/app.py",
                            root_path="/repo",
                            language="python",
                            file_size=42,
                        ),
                        chunk_id=FILE_CHUNK_ID,
                        snippet="lexical snippet",
                        token_count=2,
                        lexical_score=0.2,
                    )
                ]

            def search_vector_candidates(
                self,
                query_embedding: list[float],
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query_embedding, limit, project, root_path, language, path_prefix
                return []

        service = FilesService(
            repository=FakeRepository(),
            chunking_service=FileChunkingService(),
            project="repo-a",
        )

        result = service.search("deploy", project="repo-a", explain=True)

        self.assertIsNotNone(result.stats)
        self.assertEqual(result.stats["returned_count"], 1)

    def test_search_normalizes_relative_filters_against_root(self) -> None:
        captured: dict[str, str | None] = {}

        class FakeRepository:
            def search_lexical_candidates(
                self,
                query: str,
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query, limit, project
                captured["root_path"] = root_path
                captured["language"] = language
                captured["path_prefix"] = path_prefix
                return [
                    FileSearchCandidate(
                        file=FileListItem(
                            id=FILE_ID,
                            path="/repo/src/app.py",
                            root_path="/repo",
                            language="python",
                            file_size=42,
                        ),
                        chunk_id=FILE_CHUNK_ID,
                        snippet="lexical snippet",
                        token_count=2,
                        lexical_score=0.2,
                    )
                ]

            def search_vector_candidates(
                self,
                query_embedding: list[float],
                limit: int,
                *,
                project: str,
                root_path: str | None = None,
                language: str | None = None,
                path_prefix: str | None = None,
            ):
                del query_embedding, limit, project, root_path, language, path_prefix
                return []

        service = FilesService(repository=FakeRepository(), chunking_service=FileChunkingService(), project="repo-a")

        result = service.search("deploy", project="repo-a", root="/repo", language="python", path_prefix="src")

        self.assertEqual(result.count, 1)
        self.assertEqual(captured["root_path"], "/repo")
        self.assertEqual(captured["language"], "python")
        self.assertEqual(captured["path_prefix"], "/repo/src")

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
