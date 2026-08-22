from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from anchor.application.links.models import DocumentLinkSummary

TaskStatus = Literal["open", "in_progress", "blocked", "done", "closed"]


class TaskRecord(BaseModel):
    id: str
    project: str
    metatags: dict[str, Any]
    correlation_id: str
    title: str
    body: str
    source: str
    source_ref: str
    external_key: str | None = None
    task_kind: str
    status: TaskStatus
    priority: int
    due_at: str | None
    started_at: str | None
    completed_at: str | None
    blocked_reason: str | None
    parent_document_id: str | None
    blocked_by_document_id: str | None
    links: list[DocumentLinkSummary] = Field(default_factory=list)
    created_at: str
    updated_at: str


class TaskListItem(BaseModel):
    id: str
    title: str
    status: str
    priority: int
    links: list[DocumentLinkSummary] = Field(default_factory=list)


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
