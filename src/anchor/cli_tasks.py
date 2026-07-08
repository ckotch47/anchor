from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.tasks.models import TasksListResult, TasksSearchResult
from anchor.cli_shared import parse_metatags, resolve_project, resolve_view, response_formatter
from anchor.container import build_container

tasks_app = typer.Typer(add_completion=False, help="Tasks commands")


@tasks_app.command(name="add")
def tasks_add(
    title: Annotated[str, typer.Option("--title")],
    body: Annotated[str, typer.Option("--body")] = "",
    source: Annotated[str, typer.Option("--source")] = "cli",
    source_ref: Annotated[str, typer.Option("--source-ref")] = "",
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
    priority: Annotated[int | None, typer.Option("--priority")] = None,
    due_at: Annotated[str | None, typer.Option("--due-at")] = None,
    task_kind: Annotated[str | None, typer.Option("--task-kind")] = None,
    parent_document_id: Annotated[str | None, typer.Option("--parent-id")] = None,
    blocked_by_document_id: Annotated[str | None, typer.Option("--blocked-by-id")] = None,
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
            project=resolved_project,
            correlation_id=correlation_id,
            metatags=None if metatags is None else parse_metatags(metatags),
            task_kind=task_kind,
            priority=priority,
            due_at=due_at,
            parent_document_id=parent_document_id,
            blocked_by_document_id=blocked_by_document_id,
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
        response_formatter.emit_error("tasks", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


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
        response_formatter.emit_error("tasks", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("tasks", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("tasks", "DB_MIGRATION_FAILED", str(exc))


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
