from __future__ import annotations

import unittest

from anchor.application.files.models import FileListItem, FileSearchHit, FilesSearchResult
from anchor.application.history.models import HistoryListItem, HistorySearchHit, HistorySearchResult
from anchor.application.notes.models import NoteSearchItem, NotesSearchHit, NotesSearchResult
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
        note = NoteSearchItem(
            id="note_1",
            project=project or "repo-a",
            title="Deploy note",
            pinned=False,
            created_at="2026-06-13T00:00:00+00:00",
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


class FakeHistoryService:
    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> HistorySearchResult:
        del query, limit, budget_tokens
        history = HistoryListItem(
            id="history_1",
            project=project or "repo-a",
            entry_type="deploy_log",
            actor="agent",
            correlation_id="corr-1",
            created_at="2026-06-13T00:00:00+00:00",
        )
        return HistorySearchResult(
            query="deploy",
            count=1,
            results=[
                HistorySearchHit(
                    history=history,
                    chunk_id="chunk_4",
                    score=0.8,
                    snippet="deploy history snippet",
                )
            ],
        )


class SearchServiceTest(unittest.TestCase):
    def test_search_combines_notes_tasks_history_and_files(self) -> None:
        service = SearchService(
            FakeNotesService(),
            FakeHistoryService(),
            FakeTasksService(),
            FakeFilesService(),
            budget_tokens=100,
        )

        result = service.search(
            SearchQuery(
                query="deploy",
                project="repo-a",
                types=["notes", "tasks", "history", "files"],
                explain=True,
                budget_tokens=100,
            )
        )

        self.assertEqual(result.count, 4)
        self.assertEqual([hit.entity_type for hit in result.results], ["notes", "tasks", "history", "files"])
        self.assertIsNotNone(result.stats)
        self.assertEqual(result.stats.returned_count, 4)
        self.assertEqual(result.stats.candidate_counts["notes"], 1)
        self.assertEqual(result.stats.candidate_counts["tasks"], 1)
        self.assertEqual(result.stats.candidate_counts["history"], 1)
        self.assertEqual(result.stats.candidate_counts["files"], 1)

    def test_search_rejects_unsupported_types(self) -> None:
        service = SearchService(FakeNotesService(), FakeHistoryService(), FakeTasksService(), FakeFilesService())

        with self.assertRaises(ValueError):
            service.search(SearchQuery(query="deploy", project="repo-a", types=["unknown"], budget_tokens=100))
