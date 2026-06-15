from __future__ import annotations

import base64
import json

from anchor.adapters.sqlite_ids import ensure_uuid7_str, uuid7_str
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.system.metadata_service import MetadataSchemaService
from anchor.application.tasks.models import TaskListItem, TaskRecord, TaskSearchHit, TasksListResult, TasksSearchResult


class TasksService:
    def __init__(
        self,
        repository: SqliteTasksRepository,
        project: str,
        metadata_service: MetadataSchemaService | None = None,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._project = project
        self._metadata_service = metadata_service
        self._budget_tokens = budget_tokens

    def add(
        self,
        *,
        title: str,
        body: str = "",
        source: str = "cli",
        source_ref: str = "",
        project: str | None = None,
        correlation_id: str | None = None,
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
        resolved_correlation_id = self._resolve_correlation_id(correlation_id)
        self._validate_metatags("tasks", metatags or {})
        result = self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            project=project or self._project,
            correlation_id=resolved_correlation_id,
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
        correlation_id: str | None = None,
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
        if correlation_id is not None:
            self._validate_correlation_id(correlation_id)
        if metatags is not None:
            self._validate_metatags("tasks", metatags)
        if all(
            value is None
            for value in (
                title,
                body,
                source,
                source_ref,
                correlation_id,
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
            correlation_id=correlation_id,
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

    def get(self, task_id: str, *, project: str | None = None) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        task = self._repository.get(task_id, project=project or self._project)
        if task is None:
            raise LookupError(f"task not found: {task_id}")
        return task

    def list(
        self,
        limit: int = 20,
        *,
        project: str | None = None,
        cursor: str | None = None,
        view: str = "compact",
    ) -> TasksListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        cursor_id = self._decode_cursor(cursor)
        try:
            tasks = self._repository.list(
                limit + 1,
                project=project or self._project,
                full=view == "full",
                cursor_id=cursor_id,
            )
        except TypeError:
            tasks = self._repository.list(limit + 1, project=project or self._project)
        next_cursor = None
        if len(tasks) > limit:
            next_cursor = self._encode_cursor(tasks[limit - 1].id)
            tasks = tasks[:limit]
        return TasksListResult(
            count=len(tasks),
            tasks=tasks
            if view == "full"
            else [
                TaskListItem(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    priority=task.priority,
                )
                for task in tasks
            ],
            next_cursor=next_cursor,
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
        view: str = "compact",
        query_embedding: list[float] | None = None,
    ) -> TasksSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        del query_embedding
        results = self._trim_to_budget(
            self._repository.search(query=query, limit=limit, project=project or self._project),
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        search_results: list[TaskSearchHit] = []
        for result in results:
            task_item = result.task
            if view == "full":
                task_item = self._repository.get(result.task.id, project=project or self._project) or result.task
            search_results.append(
                TaskSearchHit(
                    task=task_item,
                    chunk_id=result.chunk_id,
                    score=result.score,
                    snippet=result.snippet,
                )
            )
        return TasksSearchResult(query=query, count=len(search_results), results=search_results)

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
    def _validate_correlation_id(correlation_id: str) -> None:
        ensure_uuid7_str(correlation_id, "correlation_id")

    def _resolve_correlation_id(self, correlation_id: str | None) -> str:
        if correlation_id is None or not correlation_id.strip():
            return uuid7_str()
        self._validate_correlation_id(correlation_id)
        return correlation_id

    def _validate_metatags(self, entity_type: str, metatags: dict[str, object]) -> None:
        if self._metadata_service is None:
            return
        self._metadata_service.validate(entity_type, metatags)

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

    @staticmethod
    def _encode_cursor(task_id: str) -> str:
        payload = json.dumps({"id": task_id}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> str | None:
        if cursor is None or not cursor.strip():
            return None
        padding = "=" * (-len(cursor) % 4)
        try:
            raw_value = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii")).decode("utf-8")
            payload = json.loads(raw_value)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("cursor must be an opaque pagination token") from exc
        if not isinstance(payload, dict):
            raise ValueError("cursor must be an opaque pagination token")
        task_id = payload.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("cursor must be an opaque pagination token")
        return task_id
