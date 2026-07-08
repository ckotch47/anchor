from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.history.models import HistorySearchResult
from anchor.cli_shared import parse_metatags, resolve_project, resolve_view, response_formatter
from anchor.container import build_container

history_app = typer.Typer(add_completion=False, help="History commands")


@history_app.command(name="append")
def history_append(
    entry_type: Annotated[str, typer.Option("--entry-type")],
    payload: Annotated[str, typer.Option("--payload")],
    actor: Annotated[str, typer.Option("--actor")] = "agent",
    project: Annotated[str | None, typer.Option("--project")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.history_service.append(
            entry_type=entry_type,
            payload=payload,
            actor=actor,
            project=resolved_project,
            metatags=parse_metatags(metatags),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "history.append",
                    {"history": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("history", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("history", "DB_MIGRATION_FAILED", str(exc))


@history_app.command(name="update")
def history_update(
    history_id: Annotated[str, typer.Option("--id")],
    entry_type: Annotated[str | None, typer.Option("--entry-type")] = None,
    payload: Annotated[str | None, typer.Option("--payload")] = None,
    actor: Annotated[str | None, typer.Option("--actor")] = None,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    metatags: Annotated[str | None, typer.Option("--metatags")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.history_service.update(
            history_id,
            entry_type=entry_type,
            payload=payload,
            actor=actor,
            correlation_id=correlation_id,
            project=resolved_project,
            metatags=parse_metatags(metatags),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "history.update",
                    {"history": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("history", "INVALID_ARGS", str(exc))
    except LookupError as exc:
        response_formatter.emit_error("history", "NOT_FOUND", str(exc))
    except Exception as exc:
        response_formatter.emit_error("history", "DB_MIGRATION_FAILED", str(exc))


@history_app.command(name="search")
def history_search(
    query: Annotated[str, typer.Option("--query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: HistorySearchResult = container.history_service.search(
            query=query,
            limit=limit,
            project=resolved_project,
            view=resolve_view(container, view),
        )
        typer.echo(
            json.dumps(
                response_formatter.format_search(
                    "history.search",
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
        response_formatter.emit_error("history", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("history", "DB_MIGRATION_FAILED", str(exc))


@history_app.command(name="delete")
def history_delete(
    history_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result = container.history_service.delete(history_id, project=resolved_project)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "history.delete",
                    {"history": result.model_dump()},
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        response_formatter.emit_error("history", "NOT_FOUND", str(exc))
    except Exception as exc:
        response_formatter.emit_error("history", "DB_MIGRATION_FAILED", str(exc))
