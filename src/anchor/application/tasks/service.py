from __future__ import annotations

import base64
import builtins
import json
import sqlite3
from typing import ClassVar

from anchor.adapters.sqlite_ids import ensure_uuid7_str, uuid7_str
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.retrieval.search_query import validate_retrieval_limit
from anchor.application.system.metadata_service import MetadataSchemaService
from anchor.application.tasks.models import (
    TaskListItem,
    TaskRecord,
    TaskSearchHit,
    TasksListResult,
    TasksSearchResult,
    TaskStatus,
)


class TasksService:
    _TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "open": {"open", "in_progress", "blocked", "done"},
        "in_progress": {"in_progress", "blocked", "done"},
        "blocked": {"blocked", "in_progress", "done"},
        "done": {"done", "closed"},
        "closed": {"closed"},
    }

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
        external_key: str | None = None,
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
        if external_key is not None:
            self._require_non_empty(external_key, "external_key")
        if parent_document_id is not None:
            ensure_uuid7_str(parent_document_id, "parent_document_id")
        if blocked_by_document_id is not None:
            ensure_uuid7_str(blocked_by_document_id, "blocked_by_document_id")
        resolved_correlation_id = uuid7_str()
        self._validate_metatags("tasks", metatags or {})
        return self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            external_key=external_key,
            project=project or self._project,
            correlation_id=resolved_correlation_id,
            metatags=metatags or {},
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
        )

    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        external_key: str | None = None,
        project: str | None = None,
        correlation_id: str | None = None,
        metatags: dict[str, object] | None = None,
        task_kind: str | None = None,
        priority: int | None = None,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
        clear_due_at: bool = False,
        clear_parent_document_id: bool = False,
        clear_blocked_by_document_id: bool = False,
        replace_nullable_fields: bool = False,
    ) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        if title is not None:
            self._require_non_empty(title, "title")
        if task_kind is not None:
            self._require_non_empty(task_kind, "task_kind")
        if external_key is not None:
            self._require_non_empty(external_key, "external_key")
        if parent_document_id is not None:
            ensure_uuid7_str(parent_document_id, "parent_document_id")
        if blocked_by_document_id is not None:
            ensure_uuid7_str(blocked_by_document_id, "blocked_by_document_id")
        if correlation_id is not None:
            self._validate_correlation_id(correlation_id)
        if metatags is not None:
            self._validate_metatags("tasks", metatags)
        if clear_due_at and due_at is not None:
            raise ValueError("due_at and clear_due_at are mutually exclusive")
        if clear_parent_document_id and parent_document_id is not None:
            raise ValueError("parent_document_id and clear_parent_document_id are mutually exclusive")
        if clear_blocked_by_document_id and blocked_by_document_id is not None:
            raise ValueError("blocked_by_document_id and clear_blocked_by_document_id are mutually exclusive")
        if not any((clear_due_at, clear_parent_document_id, clear_blocked_by_document_id)) and all(
            value is None
            for value in (
                title,
                body,
                source,
                source_ref,
                external_key,
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
            external_key=external_key,
            correlation_id=correlation_id,
            metatags=metatags,
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
            clear_due_at=clear_due_at,
            clear_parent_document_id=clear_parent_document_id,
            clear_blocked_by_document_id=clear_blocked_by_document_id,
            replace_nullable_fields=replace_nullable_fields,
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

    def get_by_external_key(
        self, external_key: str, *, project: str | None = None
    ) -> TaskRecord:
        self._require_non_empty(external_key, "external_key")
        resolved_project = project or self._project
        task = self._repository.get_by_external_key(
            external_key, project=resolved_project
        )
        if task is None:
            raise LookupError(
                f"task not found by external_key in project {resolved_project}"
            )
        return task

    def list(
        self,
        limit: int = 20,
        *,
        project: str | None = None,
        cursor: str | None = None,
        view: str = "compact",
    ) -> TasksListResult:
        limit = validate_retrieval_limit(limit)
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
        query_embedding: builtins.list[float] | None = None,
    ) -> TasksSearchResult:
        self._require_non_empty(query, "query")
        limit = validate_retrieval_limit(limit)
        del query_embedding
        results = self._trim_to_budget(
            self._repository.search(query=query, limit=limit, project=project or self._project),
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        search_results: builtins.list[TaskSearchHit] = []
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
        return self.set_status(task_id, status="done", project=project)

    def set_status(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        project: str | None = None,
        blocked_reason: str | None = None,
    ) -> TaskRecord:
        self._require_non_empty(task_id, "id")
        resolved_project = project or self._project
        current = self.get(task_id, project=resolved_project)
        if status not in self._TRANSITIONS[current.status]:
            raise ValueError(f"invalid task transition: {current.status} -> {status}")
        if status == "blocked" and (blocked_reason is None or not blocked_reason.strip()):
            raise ValueError("blocked tasks require blocked_reason")
        if status != "blocked" and blocked_reason is not None:
            raise ValueError("blocked_reason is only valid for blocked status")
        if hasattr(self._repository, "set_status"):
            task = self._repository.set_status(
                task_id,
                project=resolved_project,
                status=status,
                blocked_reason=blocked_reason,
                expected_status=current.status,
            )
        elif status == "done":
            task = self._repository.complete(task_id, project=resolved_project)
        else:
            raise RuntimeError("task repository does not support lifecycle transitions")
        if task is None:
            if self._repository.get(task_id, project=resolved_project) is not None:
                raise ValueError("task status changed concurrently")
            raise LookupError(f"task not found: {task_id}")
        return task

    def upsert(
        self,
        *,
        external_key: str,
        title: str,
        project: str | None = None,
        body: str = "",
        source: str = "anchor",
        source_ref: str = "",
        metatags: dict[str, object] | None = None,
        task_kind: str = "task",
        priority: int = 0,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord:
        self._require_non_empty(external_key, "external_key")
        resolved_project = project or self._project
        current = self._repository.get_by_external_key(external_key, project=resolved_project)
        if current is None:
            try:
                return self.add(
                    external_key=external_key,
                    title=title,
                    project=resolved_project,
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
            except sqlite3.IntegrityError:
                # A concurrent writer may have won the unique-key race.
                current = self._repository.get_by_external_key(external_key, project=resolved_project)
                if current is None:
                    raise
        return self.update(
            current.id,
            external_key=external_key,
            title=title,
            project=resolved_project,
            body=body,
            source=source,
            source_ref=source_ref,
            metatags=metatags,
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
            replace_nullable_fields=True,
        )

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

    def _validate_metatags(self, entity_type: str, metatags: dict[str, object]) -> None:
        if self._metadata_service is None:
            return
        self._metadata_service.validate(entity_type, metatags)

    @staticmethod
    def _validate_correlation_id(correlation_id: str) -> None:
        ensure_uuid7_str(correlation_id, "correlation_id")

    @staticmethod
    def _estimate_result_tokens(result: TaskSearchHit) -> int:
        return max(1, count_tokens(result.task.title) + count_tokens(result.snippet))

    def _trim_to_budget(self, results: builtins.list[TaskSearchHit], budget_tokens: int) -> builtins.list[TaskSearchHit]:
        if budget_tokens <= 0:
            return []
        trimmed: builtins.list[TaskSearchHit] = []
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
