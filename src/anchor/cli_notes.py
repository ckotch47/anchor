from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.notes.models import NotesListResult
from anchor.cli_shared import parse_metatags, resolve_project, resolve_view, response_formatter
from anchor.container import build_container

notes_app = typer.Typer(add_completion=False, help="Notes commands")


@notes_app.command(name="add")
def notes_add(
    title: Annotated[str, typer.Option("--title")],
    body: Annotated[str, typer.Option("--body")],
    source: Annotated[str, typer.Option("--source")] = "cli",
    source_ref: Annotated[str, typer.Option("--source-ref")] = "",
    pinned: Annotated[bool, typer.Option("--pinned")] = False,
    project: Annotated[str | None, typer.Option("--project")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.notes_service.add(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            project=resolved_project,
            metatags=parse_metatags(metatags),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "notes.add",
                    {"note": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="update")
def notes_update(
    note_id: Annotated[str, typer.Option("--id")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    source: Annotated[str | None, typer.Option("--source")] = None,
    source_ref: Annotated[str | None, typer.Option("--source-ref")] = None,
    pinned: Annotated[bool | None, typer.Option("--pinned/--no-pinned")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.notes_service.update(
            note_id,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            project=resolved_project,
            metatags=None if metatags is None else parse_metatags(metatags),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "notes.update",
                    {"note": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("notes", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="list")
def notes_list(
    limit: Annotated[int, typer.Option("--limit")] = 20,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: NotesListResult = container.notes_service.list(
            limit=limit,
            cursor=cursor,
            project=resolved_project,
            view=resolve_view(container, view),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "notes.list",
                    {
                        "count": result.count,
                        "notes": [note.model_dump() for note in result.notes],
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
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="get")
def notes_get(
    note_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.notes_service.get(note_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "notes.get",
                    {"note": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("notes", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="search")
def notes_search(
    query: Annotated[str, typer.Option("--query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.notes_service.search(
            query=query,
            limit=limit,
            project=resolved_project,
            view=resolve_view(container, view),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_search(
                    "notes.search",
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
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="delete")
def notes_delete(
    note_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.notes_service.delete(note_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "notes.delete",
                    {"note": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("notes", "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("notes", "DB_MIGRATION_FAILED", str(exc))
