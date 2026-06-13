from __future__ import annotations

import unittest

from anchor.application.files.models import FileListItem, FileSearchHit, FilesSearchResult
from anchor.application.notes.models import NoteRecord, NotesSearchHit, NotesSearchResult
from anchor.application.retrieval.search_query import SearchQuery
from anchor.application.retrieval.search_service import SearchService
from anchor.application.tasks.models import TaskListItem, TaskSearchHit, TasksSearchResult


class FakeNotesService:
    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> NotesSearchResult:
        del query, limit, budget_tokens
        note = NoteRecord(
            id="note_1",
            project=project or "repo-a",
            metatags={},
            title="Deploy note",
            body="deploy note body",
            source="cli",
            source_ref="",
            note_kind="note",
            pinned=False,
            archived_at=None,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )
        return NotesSearchResult(
            query="deploy",
            count=1,
            results=[
                NotesSearchHit(
                    note=note,
                    chunk_id="chunk_1",
                    score=0.95,
                    snippet="deploy note snippet",
                )
            ],
        )


class FakeTasksService:
    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> TasksSearchResult:
        del query, limit, budget_tokens
        return TasksSearchResult(
            query="deploy",
            count=1,
            results=[
                TaskSearchHit(
                    task=TaskListItem(id="task_1", title="Deploy task", status="open", priority=2),
                    chunk_id="chunk_2",
                    score=0.85,
                    snippet="deploy task snippet",
                )
            ],
        )


class FakeFilesService:
    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> FilesSearchResult:
        del query, limit, budget_tokens
        return FilesSearchResult(
            query="deploy",
            count=1,
            results=[
                FileSearchHit(
                    file=FileListItem(
                        id="file_1",
                        path="/repo/deploy.py",
                        root_path="/repo",
                        language="python",
                        file_size=42,
                    ),
                    chunk_id="chunk_3",
                    score=0.75,
                    snippet="deploy file snippet",
                )
            ],
        )


class SearchServiceTest(unittest.TestCase):
    def test_search_combines_notes_and_tasks(self) -> None:
        service = SearchService(FakeNotesService(), FakeTasksService(), FakeFilesService(), budget_tokens=100)

        result = service.search(
            SearchQuery(
                query="deploy",
                project="repo-a",
                types=["notes", "tasks", "files"],
                explain=True,
                budget_tokens=100,
            )
        )

        self.assertEqual(result.count, 3)
        self.assertEqual([hit.entity_type for hit in result.results], ["notes", "tasks", "files"])
        self.assertIsNotNone(result.stats)
        self.assertEqual(result.stats.returned_count, 3)
        self.assertEqual(result.stats.candidate_counts["notes"], 1)
        self.assertEqual(result.stats.candidate_counts["tasks"], 1)
        self.assertEqual(result.stats.candidate_counts["files"], 1)

    def test_search_rejects_unsupported_types(self) -> None:
        service = SearchService(FakeNotesService(), FakeTasksService(), FakeFilesService())

        with self.assertRaises(ValueError):
            service.search(SearchQuery(query="deploy", project="repo-a", types=["history"], budget_tokens=100))
