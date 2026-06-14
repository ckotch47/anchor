from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.retrieval.search_query import SearchQuery
from anchor.cli_shared import resolve_project, response_formatter
from anchor.container import build_container


def _parse_search_types(raw_types: str | None) -> list[str]:
    if raw_types is None or not raw_types.strip():
        return ["notes", "tasks", "history", "files"]
    return [search_type.strip() for search_type in raw_types.split(",") if search_type.strip()]


def _parse_projects(raw_projects: str | None) -> list[str] | None:
    if raw_projects is None or not raw_projects.strip():
        return None
    return [project.strip() for project in raw_projects.split(",") if project.strip()]


def search_command(
    query: Annotated[str, typer.Option("--query")],
    types: Annotated[str | None, typer.Option("--types")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    budget_tokens: Annotated[int | None, typer.Option("--budget-tokens")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    projects: Annotated[str | None, typer.Option("--projects")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    explain: Annotated[bool, typer.Option("--explain")] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        search_types = _parse_search_types(types)
        search_query = SearchQuery(
            query=query,
            types=search_types,
            project=resolved_project,
            projects=_parse_projects(projects),
            limit=limit,
            budget_tokens=budget_tokens
            if budget_tokens is not None
            else container.config.runtime.default_budget_tokens,
            explain=explain,
            cursor=cursor,
        )
        result = container.search_service.search(search_query)
        resolved_projects = search_query.projects or [resolved_project]
        typer.echo(
            json.dumps(
                response_formatter.format_search(
                    "search",
                    result,
                    container,
                    view=view,
                    project=resolved_project,
                    projects=resolved_projects,
                    types=search_types,
                    explain=explain,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("search", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("search", "DB_MIGRATION_FAILED", str(exc))
