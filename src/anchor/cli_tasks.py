from __future__ import annotations

import json
from typing import Annotated, cast

import typer

from anchor.application.tasks.models import TasksListResult, TasksSearchResult, TaskStatus
from anchor.cli_shared import parse_metatags, resolve_project, resolve_view, response_formatter
from anchor.container import build_container

tasks_app = typer.Typer(add_completion=False, help="Tasks commands")


@tasks_app.command(name="add")
def tasks_add(
    title: Annotated[str, typer.Option("--title")],
    body: Annotated[str, typer.Option("--body")] = "",
    source: Annotated[str, typer.Option("--source")] = "cli",
    source_ref: Annotated[str, typer.Option("--source-ref")] = "",
    external_key: Annotated[str | None, typer.Option("--external-key")] = None,
    priority: Annotated[int, typer.Option("--priority")] = 0,
    due_at: Annotated[str | None, typer.Option("--due-at")] = None,
    task_kind: Annotated[str, typer.Option("--task-kind")] = "task",
    parent_document_id: Annotated[str | None, typer.Option("--parent-id")] = None,
    blocked_by_document_id: Annotated[str | None, typer.Option("--blocked-by-id")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.tasks_service.add(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            external_key=external_key,
            project=resolved_project,
            metatags=parse_metatags(metatags),
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.add",
                    {"task": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="update")
def tasks_update(
    task_id: Annotated[str, typer.Option("--id")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    source: Annotated[str | None, typer.Option("--source")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref")] = None,
    external_key: Annotated[str | None, typer.Option("--external-key")] = None,
    priority: Annotated[int | None, typer.Option("--priority")] = None,
    due_at: Annotated[str | None, typer.Option("--due-at")] = None,
    task_kind: Annotated[str | None, typer.Option("--task-kind")] = None,
    parent_document_id: Annotated[str | None, typer.Option("--parent-id")] = None,
    blocked_by_document_id: Annotated[str | None, typer.Option("--blocked-by-id")] = None,
    clear_due_at: Annotated[bool, typer.Option("--clear-due-at")] = False,
    clear_parent_document_id: Annotated[bool, typer.Option("--clear-parent-id")] = False,
    clear_blocked_by_document_id: Annotated[bool, typer.Option("--clear-blocked-by-id")] = False,
    project: Annotated[str | None, typer.Option("--project")] = None,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.tasks_service.update(
            task_id,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            external_key=external_key,
            project=resolved_project,
            correlation_id=correlation_id,
            metatags=None if metatags is None else parse_metatags(metatags),
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
            clear_due_at=clear_due_at,
            clear_parent_document_id=clear_parent_document_id,
            clear_blocked_by_document_id=clear_blocked_by_document_id,
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.update",
                    {"task": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("tasks.update", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks.update", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks.update", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="get")
def tasks_get(
    task_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        resolved_view = resolve_view(container, view)
        result = container.tasks_service.get(task_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.get",
                    {"task": result.model_dump()},
                    container,
                    view=resolved_view,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("tasks.get", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks.get", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks.get", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="get-by-external-key")
def tasks_get_by_external_key(
    external_key: Annotated[str, typer.Option("--external-key")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        if project is None or not project.strip():
            raise ValueError("tasks get-by-external-key requires --project")
        container = build_container(profile=profile)
        resolved_view = resolve_view(container, view)
        result = container.tasks_service.get_by_external_key(
            external_key, project=project
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.get_by_external_key",
                    {"task": result.model_dump()},
                    container,
                    view=resolved_view,
                    extra_meta={"project": project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("tasks.get_by_external_key", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks.get_by_external_key", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks.get_by_external_key", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="list")
def tasks_list(
    limit: Annotated[int, typer.Option("--limit")] = 20,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: TasksListResult = container.tasks_service.list(
            limit=limit,
            cursor=cursor,
            project=resolved_project,
            view=resolve_view(container, view),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.list",
                    {
                        "count": result.count,
                        "tasks": [task.model_dump() for task in result.tasks],
                        **({"next_cursor": result.next_cursor} if result.next_cursor is not None else {}),
                    },
                    container,
                    view=view,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="search")
def tasks_search(
    query: Annotated[str, typer.Option("--query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: TasksSearchResult = container.tasks_service.search(
            query=query,
            limit=limit,
            project=resolved_project,
            view=resolve_view(container, view),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_search(
                    "tasks.search",
                    result,
                    container,
                    view=view,
                    project=resolved_project,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="done")
def tasks_done(
    task_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.tasks_service.done(task_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.done",
                    {"task": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("tasks", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="status")
def tasks_status(
    task_id: Annotated[str, typer.Option("--id")],
    status: Annotated[str, typer.Option("--status")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    blocked_reason: Annotated[str | None, typer.Option("--blocked-reason")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        if project is None or not project.strip():
            raise ValueError("tasks status requires --project")
        container = build_container(profile=profile)
        result = container.tasks_service.set_status(
            task_id,
            status=cast(TaskStatus, status),
            project=project,
            blocked_reason=blocked_reason,
        )
        typer.echo(json.dumps(response_formatter.format_success(
            "tasks.status", {"task": result.model_dump()}, container, extra_meta={"project": project}
        ), ensure_ascii=False, indent=2))
    except LookupError as exc:
        response_formatter.emit_error("tasks.status", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks.status", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks.status", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="upsert")
def tasks_upsert(
    external_key: Annotated[str, typer.Option("--external-key")],
    title: Annotated[str, typer.Option("--title")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    body: Annotated[str, typer.Option("--body")] = "",
    source: Annotated[str, typer.Option("--source")] = "anchor",
    source_ref: Annotated[str, typer.Option("--source-ref")] = "",
    priority: Annotated[int, typer.Option("--priority")] = 0,
    due_at: Annotated[str | None, typer.Option("--due-at")] = None,
    task_kind: Annotated[str, typer.Option("--task-kind")] = "task",
    parent_document_id: Annotated[str | None, typer.Option("--parent-id")] = None,
    blocked_by_document_id: Annotated[str | None, typer.Option("--blocked-by-id")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        if project is None or not project.strip():
            raise ValueError("tasks upsert requires --project")
        container = build_container(profile=profile)
        result = container.tasks_service.upsert(
            external_key=external_key, title=title, project=project, body=body,
            source=source, source_ref=source_ref, priority=priority, due_at=due_at,
            task_kind=task_kind, parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
            metatags=parse_metatags(metatags),
        )
        typer.echo(json.dumps(response_formatter.format_success(
            "tasks.upsert", {"task": result.model_dump()}, container, extra_meta={"project": project}
        ), ensure_ascii=False, indent=2))
    except LookupError as exc:
        response_formatter.emit_error("tasks.upsert", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks.upsert", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks.upsert", "DB_MIGRATION_FAILED", str(exc))


@tasks_app.command(name="delete")
def tasks_delete(
    task_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.tasks_service.delete(task_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "tasks.delete",
                    {"task": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("tasks", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))
