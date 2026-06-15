from __future__ import annotations

import json
from typing import Annotated

import typer

from anchor.cli_shared import response_formatter
from anchor.container import build_container

links_app = typer.Typer(add_completion=False, help="Links commands")


@links_app.command(name="add")
def links_add(
    source_id: Annotated[str, typer.Option("--source-id")],
    target_id: Annotated[str, typer.Option("--target-id")],
    relation_type: Annotated[str, typer.Option("--relation-type")],
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result = container.links_service.create(source_id=source_id, target_id=target_id, relation_type=relation_type)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "links.add",
                    {"link": result.model_dump()},
                    container,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("links", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("links", "DB_MIGRATION_FAILED", str(exc))


@links_app.command(name="list")
def links_list(
    source_id: Annotated[str | None, typer.Option("--source-id")] = None,
    target_id: Annotated[str | None, typer.Option("--target-id")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    if (source_id is None or not source_id.strip()) and (target_id is None or not target_id.strip()):
        response_formatter.emit_error("links", "INVALID_ARGS", "links list requires --source-id or --target-id")
    try:
        container = build_container(profile=profile)
        if source_id is not None and source_id.strip():
            result = container.links_service.list_by_source(source_id)
        else:
            result = container.links_service.list_by_target(target_id or "")
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "links.list",
                    {
                        "count": result.count,
                        "links": [link.model_dump() for link in result.links],
                    },
                    container,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("links", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("links", "DB_MIGRATION_FAILED", str(exc))


@links_app.command(name="delete")
def links_delete(
    source_id: Annotated[str, typer.Option("--source-id")],
    target_id: Annotated[str, typer.Option("--target-id")],
    relation_type: Annotated[str, typer.Option("--relation-type")],
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        deleted = container.links_service.delete(source_id=source_id, target_id=target_id, relation_type=relation_type)
        typer.echo(
            json.dumps(
                response_formatter.format_success(
                    "links.delete",
                    {"deleted": deleted},
                    container,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        response_formatter.emit_error("links", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("links", "DB_MIGRATION_FAILED", str(exc))
