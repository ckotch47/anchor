from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.files.models import FilesIndexResult, FilesSearchResult
from anchor.cli_shared import build_success_payload, emit_error, resolve_project
from anchor.container import build_container

files_app = typer.Typer(add_completion=False, help="Filesystem commands")


@files_app.command(name="index")
def files_index(
    root: Annotated[list[str] | None, typer.Option("--root")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: FilesIndexResult = container.files_service.index(roots=root, project=resolved_project)
        typer.echo(
            json.dumps(
                build_success_payload(
                    "files.index",
                    result.model_dump(),
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        emit_error("files", "INVALID_ARGS", str(exc))
    except Exception as exc:
        emit_error("files", "DB_MIGRATION_FAILED", str(exc))


@files_app.command(name="search")
def files_search(
    query: Annotated[str, typer.Option("--query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        result: FilesSearchResult = container.files_service.search(query=query, limit=limit, project=resolved_project)
        typer.echo(
            json.dumps(
                build_success_payload(
                    "files.search",
                    {
                        "query": result.query,
                        "count": result.count,
                        "results": [hit.model_dump() for hit in result.results],
                    },
                    container,
                    extra_meta={"project": resolved_project},
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        emit_error("files", "INVALID_ARGS", str(exc))
    except Exception as exc:
        emit_error("files", "DB_MIGRATION_FAILED", str(exc))
