from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from anchor.application.files.models import FilesGetResult, FilesListResult
from anchor.application.history.models import HistorySearchResult
from anchor.application.links.models import DocumentLinkListResult
from anchor.application.retrieval.search_query import SearchQuery
from anchor.cli_shared import resolve_project, resolve_view, response_formatter
from anchor.container import build_container

mcp_app = FastMCP(name="anchor", instructions="Local CLI tool for agents")


def _container(profile: str | None = None):
    return build_container(profile=profile)


def _tool_result(
    command: str,
    data: dict[str, Any],
    container: Any,
    *,
    project: str | None = None,
    view: str | None = None,
    extra_meta: dict[str, Any] | None = None,
    is_error: bool = False,
) -> CallToolResult:
    resolved_view = resolve_view(container, view)
    payload = response_formatter.format_success(
        command,
        data,
        container,
        view=resolved_view,
        extra_meta={"project": project or container.config.runtime.default_project},
    )
    if resolved_view == "full" and extra_meta:
        payload["meta"].update(extra_meta)
    return CallToolResult(content=[], structuredContent=payload, isError=is_error)


def _failure(command: str, code: str, message: str, container: Any) -> CallToolResult:
    return CallToolResult(
        content=[],
        structuredContent=response_formatter.format_error(command, code, message),
        isError=True,
    )


@mcp_app.tool(name="health", description="Read the local runtime and database health")
def health(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.health_service.health()
    return CallToolResult(
        content=[],
        structuredContent=response_formatter.format_success(
            "health",
            result.model_dump(),
            container,
            view=container.config.runtime.default_view,
        ),
    )


@mcp_app.tool(name="config_get", description="Read the current config")
def config_get(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.get(profile=profile)
    return CallToolResult(
        content=[], structuredContent=response_formatter.format_config("config.get", result, container)
    )


@mcp_app.tool(name="config_set", description="Update one config field")
def config_set(section: str, key: str, value: str, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.set(section=section, key=key, value=value, profile=profile)
    return CallToolResult(
        content=[], structuredContent=response_formatter.format_config("config.set", result, container)
    )


@mcp_app.tool(name="config_init", description="Initialize config from config.example.toml")
def config_init(force: bool = False, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.init(force=force)
    return CallToolResult(
        content=[], structuredContent=response_formatter.format_config("config.init", result, container)
    )


@mcp_app.tool(name="db_migrate", description="Apply pending SQLite migrations")
def db_migrate(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.migration_service.migrate()
    checkpoint = container.maintenance_service.checkpoint_wal()
    return CallToolResult(
        content=[],
        structuredContent={
            "ok": True,
            "command": "db.migrate",
            "data": {
                "database_path": result.database_path,
                "applied": result.applied,
                "current_version": result.current_version,
                "applied_versions": result.applied_versions,
                "checkpoint": checkpoint,
            },
            "meta": {
                "view": container.config.runtime.default_view,
            },
        },
    )


@mcp_app.tool(name="db_compact", description="Compact SQLite storage and rebuild retrieval indexes")
def db_compact(
    retention_days: int = 30,
    rebuild_search_indexes: bool = True,
    vacuum: bool = True,
    checkpoint: bool = True,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    if retention_days < 0:
        return _failure("db.compact", "INVALID_ARGS", "retention_days must be greater than or equal to zero", container)
    deleted_before = None
    if retention_days > 0:
        from datetime import UTC, datetime, timedelta

        deleted_before = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    result = container.maintenance_service.compact(
        deleted_before=deleted_before,
        rebuild_indexes=rebuild_search_indexes,
        vacuum=vacuum,
        checkpoint=checkpoint,
    )
    return CallToolResult(
        content=[],
        structuredContent={
            "ok": True,
            "command": "db.compact",
            "data": result.model_dump(),
            "meta": {
                "view": container.config.runtime.default_view,
            },
        },
    )


@mcp_app.tool(name="notes_add", description="Create a note")
def notes_add(
    title: str,
    body: str,
    source: str = "cli",
    source_ref: str = "",
    pinned: bool = False,
    project: str | None = None,
    correlation_id: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.add(
        title=title,
        body=body,
        source=source,
        source_ref=source_ref,
        pinned=pinned,
        project=resolved_project,
        correlation_id=correlation_id,
        metatags=metatags or {},
    )
    return _tool_result("notes.add", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_update", description="Update a note")
def notes_update(
    note_id: str,
    title: str | None = None,
    body: str | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    pinned: bool | None = None,
    project: str | None = None,
    correlation_id: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.notes_service.update(
            note_id,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            project=resolved_project,
            correlation_id=correlation_id,
            metatags=metatags,
        )
    except LookupError as exc:
        return _failure("notes.update", "NOT_FOUND", str(exc), container)
    return _tool_result("notes.update", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_list", description="List notes in the current project")
def notes_list(
    limit: int = 20,
    cursor: str | None = None,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("notes.list", "INVALID_ARGS", str(exc), container)
    result = container.notes_service.list(limit=limit, cursor=cursor, project=resolved_project, view=resolved_view)
    return _tool_result(
        "notes.list",
        {
            "count": result.count,
            "notes": [note.model_dump() for note in result.notes],
            **({"next_cursor": result.next_cursor} if result.next_cursor is not None else {}),
        },
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="notes_get", description="Get one note by id")
def notes_get(note_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.get(note_id, project=resolved_project)
    return _tool_result("notes.get", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_delete", description="Soft-delete a note")
def notes_delete(note_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.delete(note_id, project=resolved_project)
    return _tool_result("notes.delete", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_search", description="Search notes")
def notes_search(
    query: str,
    limit: int = 20,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("notes.search", "INVALID_ARGS", str(exc), container)
    result = container.notes_service.search(query=query, limit=limit, project=resolved_project, view=resolved_view)
    return _tool_result(
        "notes.search",
        response_formatter.format_search(
            "notes.search",
            result,
            container,
            view=resolved_view,
            project=resolved_project,
        )["data"],
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="history_append", description="Append a history entry")
def history_append(
    entry_type: str,
    payload: str,
    actor: str = "agent",
    correlation_id: str | None = None,
    project: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.history_service.append(
        entry_type=entry_type,
        payload=payload,
        actor=actor,
        correlation_id=correlation_id,
        project=resolved_project,
        metatags=metatags or {},
    )
    return _tool_result("history.append", {"history": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="history_update", description="Update a history entry")
def history_update(
    history_id: str,
    entry_type: str | None = None,
    payload: str | None = None,
    actor: str | None = None,
    correlation_id: str | None = None,
    project: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.history_service.update(
            history_id,
            entry_type=entry_type,
            payload=payload,
            actor=actor,
            correlation_id=correlation_id,
            project=resolved_project,
            metatags=metatags,
        )
    except LookupError as exc:
        return _failure("history.update", "NOT_FOUND", str(exc), container)
    return _tool_result("history.update", {"history": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="history_search", description="Search history entries")
def history_search(
    query: str,
    limit: int = 20,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("history.search", "INVALID_ARGS", str(exc), container)
    result: HistorySearchResult = container.history_service.search(
        query=query,
        limit=limit,
        project=resolved_project,
        view=resolved_view,
    )
    return _tool_result(
        "history.search",
        response_formatter.format_search(
            "history.search",
            result,
            container,
            view=resolved_view,
            project=resolved_project,
        )["data"],
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="history_delete", description="Delete a history entry")
def history_delete(history_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.history_service.delete(history_id, project=resolved_project)
    except LookupError as exc:
        return _failure("history.delete", "NOT_FOUND", str(exc), container)
    return _tool_result("history.delete", {"history": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_add", description="Create a task")
def tasks_add(
    title: str,
    body: str = "",
    source: str = "cli",
    source_ref: str = "",
    priority: int = 0,
    due_at: str | None = None,
    task_kind: str = "task",
    parent_document_id: str | None = None,
    blocked_by_document_id: str | None = None,
    project: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.tasks_service.add(
        title=title,
        body=body,
        source=source,
        source_ref=source_ref,
        project=resolved_project,
        metatags=metatags or {},
        task_kind=task_kind,
        priority=priority,
        due_at=due_at,
        parent_document_id=parent_document_id,
        blocked_by_document_id=blocked_by_document_id,
    )
    return _tool_result("tasks.add", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_update", description="Update a task")
def tasks_update(
    task_id: str,
    title: str | None = None,
    body: str | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    priority: int | None = None,
    due_at: str | None = None,
    task_kind: str | None = None,
    parent_document_id: str | None = None,
    blocked_by_document_id: str | None = None,
    project: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.tasks_service.update(
            task_id,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            project=resolved_project,
            metatags=metatags,
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
        )
    except LookupError as exc:
        return _failure("tasks.update", "NOT_FOUND", str(exc), container)
    return _tool_result("tasks.update", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_get", description="Get one task by id")
def tasks_get(
    task_id: str,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.tasks_service.get(task_id, project=resolved_project)
    return _tool_result(
        "tasks.get",
        {"task": result.model_dump()},
        container,
        project=resolved_project,
        view=view,
    )


@mcp_app.tool(name="tasks_list", description="List tasks in the current project")
def tasks_list(
    limit: int = 20,
    cursor: str | None = None,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("tasks.list", "INVALID_ARGS", str(exc), container)
    result = container.tasks_service.list(limit=limit, cursor=cursor, project=resolved_project, view=resolved_view)
    return _tool_result(
        "tasks.list",
        {
            "count": result.count,
            "tasks": [task.model_dump() for task in result.tasks],
            **({"next_cursor": result.next_cursor} if result.next_cursor is not None else {}),
        },
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="tasks_search", description="Search tasks")
def tasks_search(
    query: str,
    limit: int = 20,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("tasks.search", "INVALID_ARGS", str(exc), container)
    result = container.tasks_service.search(query=query, limit=limit, project=resolved_project, view=resolved_view)
    return _tool_result(
        "tasks.search",
        response_formatter.format_search(
            "tasks.search",
            result,
            container,
            view=resolved_view,
            project=resolved_project,
        )["data"],
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="tasks_done", description="Mark a task as done")
def tasks_done(task_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.tasks_service.done(task_id, project=resolved_project)
    except LookupError as exc:
        return _failure("tasks.done", "NOT_FOUND", str(exc), container)
    return _tool_result("tasks.done", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_delete", description="Soft-delete a task")
def tasks_delete(task_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.tasks_service.delete(task_id, project=resolved_project)
    except LookupError as exc:
        return _failure("tasks.delete", "NOT_FOUND", str(exc), container)
    return _tool_result("tasks.delete", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="files_index", description="Index live filesystem roots")
def files_index(
    roots: list[str] | None = None,
    project: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result = container.files_service.index(roots=roots, project=resolved_project)
    except ValueError as exc:
        return _failure("files.index", "INVALID_ARGS", str(exc), container)
    return _tool_result("files.index", result.model_dump(), container, project=resolved_project)


@mcp_app.tool(name="files_get", description="Get one indexed file by id or path")
def files_get(
    file_id: str | None = None,
    path: str | None = None,
    root: str | None = None,
    language: str | None = None,
    path_prefix: str | None = None,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("files.get", "INVALID_ARGS", str(exc), container)
    try:
        result: FilesGetResult = container.files_service.get(
            file_id=file_id,
            path=path,
            root=root,
            language=language,
            path_prefix=path_prefix,
            project=resolved_project,
        )
    except LookupError as exc:
        return _failure("files.get", "NOT_FOUND", str(exc), container)
    except ValueError as exc:
        return _failure("files.get", "INVALID_ARGS", str(exc), container)
    return _tool_result(
        "files.get", {"file": result.file.model_dump()}, container, project=resolved_project, view=resolved_view
    )


@mcp_app.tool(name="files_delete", description="Delete one indexed file by id or path")
def files_delete(
    file_id: str | None = None,
    path: str | None = None,
    root: str | None = None,
    language: str | None = None,
    path_prefix: str | None = None,
    project: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        result: FilesGetResult = container.files_service.delete(
            file_id=file_id,
            path=path,
            root=root,
            language=language,
            path_prefix=path_prefix,
            project=resolved_project,
        )
    except LookupError as exc:
        return _failure("files.delete", "NOT_FOUND", str(exc), container)
    except ValueError as exc:
        return _failure("files.delete", "INVALID_ARGS", str(exc), container)
    return _tool_result("files.delete", {"file": result.file.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="files_list", description="List indexed files in the current project")
def files_list(
    limit: int = 20,
    cursor: str | None = None,
    root: str | None = None,
    language: str | None = None,
    path_prefix: str | None = None,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("files.list", "INVALID_ARGS", str(exc), container)
    try:
        result: FilesListResult = container.files_service.list(
            limit=limit,
            cursor=cursor,
            root=root,
            language=language,
            path_prefix=path_prefix,
            project=resolved_project,
            view=resolved_view,
        )
    except ValueError as exc:
        return _failure("files.list", "INVALID_ARGS", str(exc), container)
    return _tool_result(
        "files.list",
        {
            "count": result.count,
            "files": [file.model_dump() for file in result.files],
            **({"next_cursor": result.next_cursor} if result.next_cursor is not None else {}),
        },
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="files_search", description="Search indexed files")
def files_search(
    query: str,
    limit: int = 20,
    root: str | None = None,
    language: str | None = None,
    path_prefix: str | None = None,
    explain: bool = False,
    project: str | None = None,
    view: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        resolved_view = resolve_view(container, view)
    except ValueError as exc:
        return _failure("files.search", "INVALID_ARGS", str(exc), container)
    try:
        result = container.files_service.search(
            query=query,
            limit=limit,
            root=root,
            language=language,
            path_prefix=path_prefix,
            explain=explain,
            project=resolved_project,
            view=resolved_view,
        )
    except ValueError as exc:
        return _failure("files.search", "INVALID_ARGS", str(exc), container)
    return _tool_result(
        "files.search",
        response_formatter.format_search(
            "files.search",
            result,
            container,
            view=resolved_view,
            project=resolved_project,
            explain=explain,
        )["data"],
        container,
        project=resolved_project,
        view=resolved_view,
    )


@mcp_app.tool(name="links_add", description="Create a typed link between two documents")
def links_add(source_id: str, target_id: str, relation_type: str, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    try:
        result = container.links_service.create(source_id=source_id, target_id=target_id, relation_type=relation_type)
    except ValueError as exc:
        return _failure("links.add", "INVALID_ARGS", str(exc), container)
    return _tool_result("links.add", {"link": result.model_dump()}, container)


@mcp_app.tool(name="links_list", description="List links by source or target document id")
def links_list(
    source_id: str | None = None,
    target_id: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    if source_id is None and target_id is None:
        return _failure("links.list", "INVALID_ARGS", "links list requires source_id or target_id", container)
    try:
        if source_id is not None:
            result: DocumentLinkListResult = container.links_service.list_by_source(source_id)
        else:
            result = container.links_service.list_by_target(target_id or "")
    except ValueError as exc:
        return _failure("links.list", "INVALID_ARGS", str(exc), container)
    return _tool_result("links.list", {"count": result.count, "links": [link.model_dump() for link in result.links]}, container)


@mcp_app.tool(name="links_delete", description="Delete a typed link between two documents")
def links_delete(source_id: str, target_id: str, relation_type: str, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    try:
        deleted = container.links_service.delete(source_id=source_id, target_id=target_id, relation_type=relation_type)
    except ValueError as exc:
        return _failure("links.delete", "INVALID_ARGS", str(exc), container)
    return _tool_result("links.delete", {"deleted": deleted}, container)


@mcp_app.tool(name="search", description="Cross-entity retrieval across notes, tasks, history, and files")
def search(
    query: str,
    types: list[str] | None = None,
    limit: int = 20,
    budget_tokens: int | None = None,
    cursor: str | None = None,
    projects: list[str] | None = None,
    project: str | None = None,
    view: str | None = None,
    explain: bool = False,
    profile: str | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    try:
        search_query = SearchQuery(
            query=query,
            types=types or ["notes", "tasks", "history", "files"],
            project=resolved_project,
            projects=projects,
            limit=limit,
            budget_tokens=budget_tokens
            if budget_tokens is not None
            else container.config.runtime.default_budget_tokens,
            explain=explain,
            cursor=cursor,
            weights=weights or {},
        )
        result = container.search_service.search(search_query)
        return _tool_result(
            "search",
            response_formatter.format_search(
                "search",
                result,
                container,
                view=view,
                project=resolved_project,
                projects=search_query.projects or [resolved_project],
                types=search_query.types,
                explain=explain,
            )["data"],
            container,
            view=view,
        )
    except ValueError as exc:
        return _failure("search", "INVALID_ARGS", str(exc), container)


def run_stdio() -> None:
    mcp_app.run("stdio")
