from __future__ import annotations

import unittest

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.application.files.models import FileListItem, FileSearchHit, FilesSearchResult
from anchor.application.history.models import HistoryListItem, HistorySearchHit, HistorySearchResult
from anchor.application.notes.models import NoteSearchItem, NotesSearchHit, NotesSearchResult
from anchor.application.retrieval.search_query import SearchQuery
from anchor.application.retrieval.search_service import SearchService
from anchor.application.tasks.models import TaskListItem, TaskSearchHit, TasksSearchResult

NOTE_ID = uuid7_str()
NOTE_CHUNK_ID = uuid7_str()
TASK_ID = uuid7_str()
TASK_CHUNK_ID = uuid7_str()
FILE_ID = uuid7_str()
FILE_CHUNK_ID = uuid7_str()
HISTORY_ID = uuid7_str()
HISTORY_CHUNK_ID = uuid7_str()
HISTORY_CORRELATION_ID = uuid7_str()


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
            id=NOTE_ID,
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
                    chunk_id=NOTE_CHUNK_ID,
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
                    task=TaskListItem(id=TASK_ID, title="Deploy task", status="open", priority=2),
                    chunk_id=TASK_CHUNK_ID,
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
                        id=FILE_ID,
                        path="/repo/deploy.py",
                        root_path="/repo",
                        language="python",
                        file_size=42,
                    ),
                    chunk_id=FILE_CHUNK_ID,
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
            id=HISTORY_ID,
            project=project or "repo-a",
            entry_type="deploy_log",
            actor="agent",
            correlation_id=HISTORY_CORRELATION_ID,
            created_at="2026-06-13T00:00:00+00:00",
        )
        return HistorySearchResult(
            query="deploy",
            count=1,
            results=[
                HistorySearchHit(
                    history=history,
                    chunk_id=HISTORY_CHUNK_ID,
                    score=0.8,
                    snippet="deploy history snippet",
                )
            ],
        )


class EmptyService:
    def search(self, *args, **kwargs):
        del args, kwargs
        return NotesSearchResult(query="deploy", count=0, results=[])


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

    def test_search_supports_cursor_pagination(self) -> None:
        class PagingNotesService:
            def search(
                self,
                query: str,
                limit: int = 20,
                *,
                project: str | None = None,
                budget_tokens: int | None = None,
            ) -> NotesSearchResult:
                del query, budget_tokens
                items = [
                    NotesSearchHit(
                        note=NoteSearchItem(
                            id=NOTE_ID,
                            project=project or "repo-a",
                            title="A",
                            pinned=False,
                            created_at="2026-06-13T00:00:00+00:00",
                        ),
                        chunk_id=NOTE_CHUNK_ID,
                        score=0.9,
                        snippet="a",
                    ),
                    NotesSearchHit(
                        note=NoteSearchItem(
                            id=uuid7_str(),
                            project=project or "repo-a",
                            title="B",
                            pinned=False,
                            created_at="2026-06-13T00:00:00+00:00",
                        ),
                        chunk_id=uuid7_str(),
                        score=0.9,
                        snippet="b",
                    ),
                ]
                return NotesSearchResult(query="deploy", count=len(items), results=items[:limit])

        service = SearchService(
            PagingNotesService(),
            EmptyService(),
            EmptyService(),
            EmptyService(),
            budget_tokens=100,
        )

        first_page = service.search(
            SearchQuery(query="deploy", project="repo-a", types=["notes"], limit=1, budget_tokens=100)
        )
        second_page = service.search(
            SearchQuery(
                query="deploy",
                project="repo-a",
                types=["notes"],
                limit=1,
                budget_tokens=100,
                cursor=first_page.next_cursor,
            )
        )

        self.assertEqual(first_page.count, 1)
        self.assertIsNotNone(first_page.next_cursor)
        self.assertEqual(second_page.count, 1)
        self.assertIsNone(second_page.next_cursor)

    def test_search_supports_explicit_cross_project_scope(self) -> None:
        class CrossProjectNotesService:
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
                    id=f"{project}-note",
                    project=project or "repo-a",
                    title=f"{project} note",
                    pinned=False,
                    created_at="2026-06-13T00:00:00+00:00",
                )
                return NotesSearchResult(
                    query="deploy",
                    count=1,
                    results=[
                        NotesSearchHit(
                            note=note,
                            chunk_id=f"{project}-chunk",
                            score=0.9,
                            snippet=f"{project} snippet",
                        )
                    ],
                )

        service = SearchService(
            CrossProjectNotesService(),
            EmptyService(),
            EmptyService(),
            EmptyService(),
            budget_tokens=100,
        )

        result = service.search(
            SearchQuery(
                query="deploy",
                project="repo-a",
                projects=["repo-a", "repo-b"],
                types=["notes"],
                limit=10,
                budget_tokens=100,
                explain=True,
            )
        )

        self.assertEqual(result.count, 2)
        self.assertEqual({hit.project for hit in result.results}, {"repo-a", "repo-b"})
        self.assertEqual(result.stats.candidate_counts["notes"], 2)
