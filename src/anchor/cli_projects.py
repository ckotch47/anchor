from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.application.system.projects_service import ProjectsListResult
from anchor.cli_shared import response_formatter
from anchor.container import build_container

projects_app = typer.Typer(add_completion=False, help="Projects commands")


@projects_app.command(name="list")
def projects_list(
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result: ProjectsListResult = container.projects_service.list_projects()
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "projects.list",
                    {
                        "count": result.count,
                        "projects": result.projects,
                    },
                    container,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:
        response_formatter.emit_error("projects", "DB_MIGRATION_FAILED", str(exc))
