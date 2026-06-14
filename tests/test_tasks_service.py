from __future__ import annotations

import unittest

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.application.tasks.models import TaskListItem, TaskRecord, TaskSearchHit
from anchor.application.tasks.service import TasksService

TASK_ID = uuid7_str()
TASK_LIST_ID = uuid7_str()
TASK_OTHER_ID = uuid7_str()
TASK_CHUNK_ID = uuid7_str()
TASK_PARENT_ID = uuid7_str()
TASK_BLOCKED_BY_ID = uuid7_str()


class FakeTasksRepository:
    def __init__(self) -> None:
        self.created: TaskRecord | None = None
        self.completed: TaskRecord | None = None
        self.updated: TaskRecord | None = None

    def create(
        self,
        *,
        title: str,
        body: str,
        source: str,
        source_ref: str,
        project: str,
        metatags: dict[str, object] | None = None,
        task_kind: str = "task",
        priority: int = 0,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord:
        self.created = TaskRecord(
            id=TASK_ID,
            project=project,
            metatags=metatags or {},
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            task_kind=task_kind,
            status="open",
            priority=priority,
            due_at=due_at,
            started_at=None,
            completed_at=None,
            blocked_reason=None,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )
        return self.created

    def list(self, limit: int, *, project: str):
        return [
            TaskListItem(
                id=TASK_LIST_ID,
                title="Task one",
                status="open",
                priority=0,
            )
        ][:limit]

    def get(self, task_id: str, *, project: str):  # pragma: no cover - not used in test
        return self.created if self.created and self.created.id == task_id else None

    def complete(self, task_id: str, *, project: str) -> TaskRecord | None:
        if self.created is None or self.created.id != task_id:
            return None
        self.completed = self.created.model_copy(update={"status": "done", "completed_at": "2026-06-13T00:10:00+00:00"})
        return self.completed

    def update(
        self,
        task_id: str,
        *,
        project: str,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        metatags: dict[str, object] | None = None,
        task_kind: str | None = None,
        priority: int | None = None,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord | None:
        if self.created is None or self.created.id != task_id:
            return None
        self.updated = self.created.model_copy(
            update={
                "project": project,
                "title": title if title is not None else self.created.title,
                "body": body if body is not None else self.created.body,
                "source": source if source is not None else self.created.source,
                "source_ref": source_ref if source_ref is not None else self.created.source_ref,
                "metatags": metatags if metatags is not None else self.created.metatags,
                "task_kind": task_kind if task_kind is not None else self.created.task_kind,
                "priority": priority if priority is not None else self.created.priority,
                "due_at": due_at if due_at is not None else self.created.due_at,
                "parent_document_id": (
                    parent_document_id if parent_document_id is not None else self.created.parent_document_id
                ),
                "blocked_by_document_id": (
                    blocked_by_document_id if blocked_by_document_id is not None else self.created.blocked_by_document_id
                ),
            }
        )
        self.created = self.updated
        return self.updated

    def search(self, query: str, limit: int, *, project: str):
        del query, project
        return [
            TaskSearchHit(
                task=TaskListItem(id=TASK_ID, title="Task one", status="open", priority=0),
                chunk_id=TASK_CHUNK_ID,
                score=0.9,
                snippet="Task one snippet",
            )
        ][:limit]

    def delete(self, task_id: str, *, project: str) -> TaskRecord | None:
        del project
        if self.created is None or self.created.id != task_id:
            return None
        deleted = self.created
        self.created = None
        return deleted


class BudgetedTasksRepository(FakeTasksRepository):
    def search(self, query: str, limit: int, *, project: str):
        del query, project
        return [
            TaskSearchHit(
                task=TaskListItem(id=TASK_ID, title="Task one", status="open", priority=0),
                chunk_id=TASK_CHUNK_ID,
                score=0.9,
                snippet="Task one snippet with extra words",
            ),
            TaskSearchHit(
                task=TaskListItem(id=TASK_OTHER_ID, title="Task two", status="open", priority=0),
                chunk_id=uuid7_str(),
                score=0.8,
                snippet="Task two snippet with extra words",
            ),
        ][:limit]


class TasksServiceTest(unittest.TestCase):
    def test_add_list_and_done_flow(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        task = service.add(
            title="Ship tasks",
            body="Implement task slice",
            project="repo-a",
            metatags={"topic": "tasks"},
            task_kind="task",
            priority=3,
            due_at="2026-06-30T00:00:00+00:00",
            parent_document_id=TASK_PARENT_ID,
            blocked_by_document_id=TASK_BLOCKED_BY_ID,
        )
        listing = service.list(project="repo-a")
        done = service.done(TASK_ID, project="repo-a")

        self.assertEqual(task.id, TASK_ID)
        self.assertEqual(task.project, "repo-a")
        self.assertEqual(task.metatags, {"topic": "tasks"})
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.parent_document_id, TASK_PARENT_ID)
        self.assertEqual(task.blocked_by_document_id, TASK_BLOCKED_BY_ID)
        self.assertEqual(listing.count, 1)
        self.assertEqual(listing.tasks[0].id, TASK_LIST_ID)
        self.assertEqual(done.status, "done")
        self.assertIsNotNone(repo.completed)

    def test_search_returns_compact_hits(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        result = service.search("deploy", project="repo-a")

        self.assertEqual(result.query, "deploy")
        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].task.title, "Task one")

    def test_search_trims_to_budget(self) -> None:
        repo = BudgetedTasksRepository()
        service = TasksService(repository=repo, project="workspace", budget_tokens=8)

        result = service.search("deploy", project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].task.id, TASK_ID)

    def test_update_changes_fields(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        service.add(title="Ship tasks", body="Implement task slice", project="repo-a")
        updated = service.update(
            TASK_ID,
            title="Ship tasks v2",
            priority=5,
            due_at="2026-07-01T00:00:00+00:00",
            metatags={"topic": "tasks"},
            project="repo-a",
        )

        self.assertEqual(updated.title, "Ship tasks v2")
        self.assertEqual(updated.priority, 5)
        self.assertEqual(updated.due_at, "2026-07-01T00:00:00+00:00")
        self.assertEqual(updated.metatags, {"topic": "tasks"})

    def test_update_rejects_empty_payload(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        service.add(title="Ship tasks", body="Implement task slice", project="repo-a")

        with self.assertRaises(ValueError):
            service.update(TASK_ID, project="repo-a")

    def test_add_rejects_empty_title(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        with self.assertRaises(ValueError):
            service.add(title=" ", body="text")

    def test_add_rejects_non_uuidv7_parent_reference(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        with self.assertRaises(ValueError):
            service.add(title="Ship tasks", body="Implement task slice", project="repo-a", parent_document_id="not-a-uuid")

    def test_delete_removes_task(self) -> None:
        repo = FakeTasksRepository()
        service = TasksService(repository=repo, project="workspace")

        service.add(title="Ship tasks", body="Implement task slice", project="repo-a")
        deleted = service.delete(TASK_ID, project="repo-a")

        self.assertEqual(deleted.id, TASK_ID)
        self.assertIsNone(repo.created)
        with self.assertRaises(LookupError):
            service.done(TASK_ID, project="repo-a")
