from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.retrieval.search_query import SearchQuery
from anchor.cli_shared import build_success_payload, emit_error, resolve_project
from anchor.container import build_container


def _parse_search_types(raw_types: str | None) -> list[str]:
    if raw_types is None or not raw_types.strip():
        return ["notes", "tasks"]
    return [search_type.strip() for search_type in raw_types.split(",") if search_type.strip()]


def _render_search_payload(result: object, container: object, resolved_project: str, explain: bool, search_types: list[str]) -> None:
    data = result.model_dump(exclude_none=True)
    if not explain and isinstance(data, dict):
        stats = data.get("stats")
        if stats is None:
            data.pop("stats", None)
    typer.echo(
        json.dumps(
            build_success_payload(
                "search",
                data,
                container,
                extra_meta={"project": resolved_project, "types": search_types, "explain": explain},
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def search_command(
    query: Annotated[str, typer.Option("--query")],
    types: Annotated[str | None, typer.Option("--types")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    budget_tokens: Annotated[int | None, typer.Option("--budget-tokens")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
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
            limit=limit,
            budget_tokens=budget_tokens if budget_tokens is not None else container.config.runtime.default_budget_tokens,
            explain=explain,
        )
        result = container.search_service.search(search_query)
        _render_search_payload(result, container, resolved_project, explain, search_types)
    except ValueError as exc:
        emit_error("search", "INVALID_ARGS", str(exc))
    except Exception as exc:
        emit_error("search", "DB_MIGRATION_FAILED", str(exc))
