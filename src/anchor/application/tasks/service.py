from __future__ import annotations

from anchor.adapters.sqlite_ids import ensure_uuid7_str
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.tasks.models import TaskListItem, TaskRecord, TaskSearchHit, TasksListResult, TasksSearchResult


class TasksService:
    def __init__(
        self,
        repository: SqliteTasksRepository,
        project: str,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._project = project
        self._budget_tokens = budget_tokens

    def add(
        self,
        *,
        title: str,
        body: str = "",
        source: str = "cli",
        source_ref: str = "",
        project: str | None = None,
        metatags: dict[str, object] | None = None,
        task_kind: str = "task",
        priority: int = 0,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord:
        self._require_non_empty(title, "title")
        self._require_non_empty(task_kind, "task_kind")
        if parent_document_id is not None:
            ensure_uuid7_str(parent_document_id, "parent_document_id")
        if blocked_by_document_id is not None:
            ensure_uuid7_str(blocked_by_document_id, "blocked_by_document_id")
        result = self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            project=project or self._project,
            metatags=metatags or {},
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
        )
        return result

    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        project: str | None = None,
        metatags: dict[str, object] | None = None,
        task_kind: str | None = None,
        priority: int | None = None,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        if title is not None:
            self._require_non_empty(title, "title")
        if task_kind is not None:
            self._require_non_empty(task_kind, "task_kind")
        if parent_document_id is not None:
            ensure_uuid7_str(parent_document_id, "parent_document_id")
        if blocked_by_document_id is not None:
            ensure_uuid7_str(blocked_by_document_id, "blocked_by_document_id")
        if all(
            value is None
            for value in (
                title,
                body,
                source,
                source_ref,
                metatags,
                task_kind,
                priority,
                due_at,
                parent_document_id,
                blocked_by_document_id,
            )
        ):
            raise ValueError("update requires at least one field")
        resolved_project = project or self._project
        result = self._repository.update(
            task_id,
            project=resolved_project,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            metatags=metatags,
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
        )
        if result is None:
            raise LookupError(f"task not found: {task_id}")
        return result

    def list(self, limit: int = 20, *, project: str | None = None, view: str = "compact") -> TasksListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        try:
            tasks = self._repository.list(limit, project=project or self._project, full=view == "full")
        except TypeError:
            tasks = self._repository.list(limit, project=project or self._project)
        return TasksListResult(
            count=len(tasks),
            tasks=tasks if view == "full" else [
                TaskListItem(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    priority=task.priority,
                )
                for task in tasks
            ],
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
        view: str = "compact",
    ) -> TasksSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        results = self._trim_to_budget(
            self._repository.search(query=query, limit=limit, project=project or self._project),
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        if view == "full":
            results = [
                TaskSearchHit(
                    task=self._repository.get(result.task.id, project=project or self._project) or result.task,
                    chunk_id=result.chunk_id,
                    score=result.score,
                    snippet=result.snippet,
                )
                for result in results
            ]
        return TasksSearchResult(query=query, count=len(results), results=results)

    def done(self, task_id: str, *, project: str | None = None) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        task = self._repository.complete(task_id, project=project or self._project)
        if task is None:
            raise LookupError(f"task not found: {task_id}")
        return task

    def delete(self, task_id: str, *, project: str | None = None) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        deleted = self._repository.delete(task_id, project=project or self._project)
        if deleted is None:
            raise LookupError(f"task not found: {task_id}")
        return deleted

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

    @staticmethod
    def _estimate_result_tokens(result: TaskSearchHit) -> int:
        return max(1, count_tokens(result.task.title) + count_tokens(result.snippet))

    def _trim_to_budget(self, results: list[TaskSearchHit], budget_tokens: int) -> list[TaskSearchHit]:
        if budget_tokens <= 0:
            return []
        trimmed: list[TaskSearchHit] = []
        total_tokens = 0
        for result in results:
            result_cost = self._estimate_result_tokens(result)
            if trimmed and total_tokens + result_cost > budget_tokens:
                break
            trimmed.append(result)
            total_tokens += result_cost
        return trimmed
