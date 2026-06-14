from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TaskRecord(BaseModel):
    id: str
    project: str
    metatags: dict[str, Any]
    correlation_id: str
    title: str
    body: str
    source: str
    source_ref: str
    task_kind: str
    status: str
    priority: int
    due_at: str | None
    started_at: str | None
    completed_at: str | None
    blocked_reason: str | None
    parent_document_id: str | None
    blocked_by_document_id: str | None
    created_at: str
    updated_at: str


class TaskListItem(BaseModel):
    id: str
    title: str
    status: str
    priority: int


class TaskSearchHit(BaseModel):
    task: TaskRecord | TaskListItem
    chunk_id: str
    score: float
    snippet: str


class TasksListResult(BaseModel):
    count: int
    tasks: list[TaskRecord | TaskListItem]
    next_cursor: str | None = None


class TasksSearchResult(BaseModel):
    query: str
    count: int
    results: list[TaskSearchHit]
