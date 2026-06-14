from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from anchor.application.history.models import HistorySearchResult
from anchor.application.retrieval.search_query import SearchQuery
from anchor.cli_shared import build_success_payload, config_payload, resolve_project, resolve_view
from anchor.container import build_container

mcp_app = FastMCP(name="anchor", instructions="Local CLI tool for agents")


def _container(profile: str | None = None):
    return build_container(profile=profile)


def _success(command: str, data: dict[str, Any], container: Any, *, project: str | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_success_payload(command, data, container, extra_meta={"project": project or container.config.runtime.default_project, **(extra_meta or {})})


def _error(command: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "error": {
            "code": code,
            "message": message,
            "retryable": False,
        },
    }


@mcp_app.tool(name="health", description="Read the local runtime and database health")
def health(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.health_service.health()
    return {
        "ok": True,
        "command": "health",
        "data": result.model_dump(),
        "meta": {
            "view": container.config.runtime.default_view,
            "profile": container.profile_name,
            "config_path": str(container.config_path),
        },
    }


@mcp_app.tool(name="config_get", description="Read the current config")
def config_get(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.get(profile=profile)
    return config_payload("config.get", result, container)


@mcp_app.tool(name="config_set", description="Update one config field")
def config_set(section: str, key: str, value: str, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.set(section=section, key=key, value=value, profile=profile)
    return config_payload("config.set", result, container)


@mcp_app.tool(name="config_init", description="Initialize config from config.example.toml")
def config_init(force: bool = False, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.config_service.init(force=force)
    return {
        "ok": True,
        "command": "config.init",
        "data": {
            "config": result.config.model_dump(),
            "config_path": result.config_path,
            "profile_name": result.profile_name,
        },
        "meta": {
            "view": result.config.runtime.default_view,
            "profile": container.profile_name,
        },
    }


@mcp_app.tool(name="db_migrate", description="Apply pending SQLite migrations")
def db_migrate(profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    result = container.migration_service.migrate()
    return {
        "ok": True,
        "command": "db.migrate",
        "data": {
            "database_path": result.database_path,
            "applied": result.applied,
            "current_version": result.current_version,
            "applied_versions": result.applied_versions,
        },
        "meta": {
            "view": container.config.runtime.default_view,
            "profile": container.profile_name,
        },
    }


@mcp_app.tool(name="notes_add", description="Create a note")
def notes_add(
    title: str,
    body: str,
    source: str = "cli",
    source_ref: str = "",
    pinned: bool = False,
    project: str | None = None,
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
        metatags=metatags or {},
    )
    return _success("notes.add", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_update", description="Update a note")
def notes_update(
    note_id: str,
    title: str | None = None,
    body: str | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    pinned: bool | None = None,
    project: str | None = None,
    metatags: dict[str, object] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.update(
        note_id,
        title=title,
        body=body,
        source=source,
        source_ref=source_ref,
        pinned=pinned,
        project=resolved_project,
        metatags=metatags,
    )
    return _success("notes.update", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_list", description="List notes in the current project")
def notes_list(
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
        return _error("notes.list", "INVALID_ARGS", str(exc))
    result = container.notes_service.list(limit=limit, project=resolved_project, view=resolved_view)
    return _success(
        "notes.list",
        {"count": result.count, "notes": [note.model_dump() for note in result.notes]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
    )


@mcp_app.tool(name="notes_get", description="Get one note by id")
def notes_get(note_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.get(note_id, project=resolved_project)
    return _success("notes.get", {"note": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="notes_delete", description="Soft-delete a note")
def notes_delete(note_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.notes_service.delete(note_id, project=resolved_project)
    return _success("notes.delete", {"note": result.model_dump()}, container, project=resolved_project)


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
        return _error("notes.search", "INVALID_ARGS", str(exc))
    result = container.notes_service.search(query=query, limit=limit, project=resolved_project, view=resolved_view)
    return _success(
        "notes.search",
        {"query": result.query, "count": result.count, "results": [hit.model_dump() for hit in result.results]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
    )


@mcp_app.tool(name="history_append", description="Append a history entry")
def history_append(
    entry_type: str,
    payload: str,
    actor: str = "agent",
    correlation_id: str = "",
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
    return _success("history.append", {"history": result.model_dump()}, container, project=resolved_project)


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
    result = container.history_service.update(
        history_id,
        entry_type=entry_type,
        payload=payload,
        actor=actor,
        correlation_id=correlation_id,
        project=resolved_project,
        metatags=metatags,
    )
    return _success("history.update", {"history": result.model_dump()}, container, project=resolved_project)


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
        return _error("history.search", "INVALID_ARGS", str(exc))
    result: HistorySearchResult = container.history_service.search(
        query=query,
        limit=limit,
        project=resolved_project,
        view=resolved_view,
    )
    return _success(
        "history.search",
        {"query": result.query, "count": result.count, "results": [hit.model_dump() for hit in result.results]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
    )


@mcp_app.tool(name="history_delete", description="Delete a history entry")
def history_delete(history_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.history_service.delete(history_id, project=resolved_project)
    return _success("history.delete", {"history": result.model_dump()}, container, project=resolved_project)


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
    return _success("tasks.add", {"task": result.model_dump()}, container, project=resolved_project)


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
    return _success("tasks.update", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_list", description="List tasks in the current project")
def tasks_list(
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
        return _error("tasks.list", "INVALID_ARGS", str(exc))
    result = container.tasks_service.list(limit=limit, project=resolved_project, view=resolved_view)
    return _success(
        "tasks.list",
        {"count": result.count, "tasks": [task.model_dump() for task in result.tasks]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
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
        return _error("tasks.search", "INVALID_ARGS", str(exc))
    result = container.tasks_service.search(query=query, limit=limit, project=resolved_project, view=resolved_view)
    return _success(
        "tasks.search",
        {"query": result.query, "count": result.count, "results": [hit.model_dump() for hit in result.results]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
    )


@mcp_app.tool(name="tasks_done", description="Mark a task as done")
def tasks_done(task_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.tasks_service.done(task_id, project=resolved_project)
    return _success("tasks.done", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="tasks_delete", description="Soft-delete a task")
def tasks_delete(task_id: str, project: str | None = None, profile: str | None = None) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.tasks_service.delete(task_id, project=resolved_project)
    return _success("tasks.delete", {"task": result.model_dump()}, container, project=resolved_project)


@mcp_app.tool(name="files_index", description="Index live filesystem roots")
def files_index(
    roots: list[str] | None = None,
    project: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    container = _container(profile)
    resolved_project = resolve_project(container, project)
    result = container.files_service.index(roots=roots, project=resolved_project)
    return _success("files.index", result.model_dump(), container, project=resolved_project)


@mcp_app.tool(name="files_search", description="Search indexed files")
def files_search(
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
        return _error("files.search", "INVALID_ARGS", str(exc))
    result = container.files_service.search(query=query, limit=limit, project=resolved_project, view=resolved_view)
    return _success(
        "files.search",
        {"query": result.query, "count": result.count, "results": [hit.model_dump() for hit in result.results]},
        container,
        project=resolved_project,
        extra_meta={"view": resolved_view},
    )


@mcp_app.tool(name="search", description="Cross-entity retrieval across notes, tasks, history, and files")
def search(
    query: str,
    types: list[str] | None = None,
    limit: int = 20,
    budget_tokens: int | None = None,
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
            limit=limit,
            budget_tokens=budget_tokens if budget_tokens is not None else container.config.runtime.default_budget_tokens,
            explain=explain,
            weights=weights or {},
        )
        result = container.search_service.search(search_query)
        data = result.model_dump(exclude_none=True)
        if not explain and isinstance(data, dict):
            data.pop("stats", None)
        return build_success_payload(
            "search",
            data,
            container,
            view=view,
            extra_meta={"project": resolved_project, "types": search_query.types, "explain": explain},
        )
    except ValueError as exc:
        return _error("search", "INVALID_ARGS", str(exc))


def run_stdio() -> None:
    mcp_app.run("stdio")
