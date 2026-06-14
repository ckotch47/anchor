from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from anchor.cli_files import files_app, files_delete, files_get, files_index, files_list, files_search
from anchor.cli_history import history_app, history_append, history_delete, history_search, history_update
from anchor.cli_notes import notes_add, notes_app, notes_delete, notes_get, notes_list, notes_search, notes_update
from anchor.cli_search import search_command
from anchor.cli_shared import response_formatter
from anchor.cli_tasks import tasks_add, tasks_app, tasks_delete, tasks_done, tasks_list, tasks_search, tasks_update
from anchor.container import build_container
from anchor.mcp_server import run_stdio

app = typer.Typer(add_completion=False, help="Qatoria Anchor")
app.add_typer(notes_app, name="notes")
app.add_typer(history_app, name="history")
app.add_typer(files_app, name="files")
app.add_typer(tasks_app, name="tasks")
app.command(name="search")(search_command)

__all__ = [
    "app",
    "config_command",
    "db_command",
    "files_delete",
    "files_get",
    "files_index",
    "files_list",
    "files_search",
    "health",
    "history_append",
    "history_delete",
    "history_search",
    "history_update",
    "mcp_command",
    "notes_add",
    "notes_delete",
    "notes_get",
    "notes_list",
    "notes_search",
    "notes_update",
    "search",
    "tasks_add",
    "tasks_delete",
    "tasks_done",
    "tasks_list",
    "tasks_search",
    "tasks_update",
]

search = search_command


@app.command()
def health(
    format: Annotated[str, typer.Option("--format")] = "json",
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result = container.health_service.health()
        payload: dict[str, Any] = {
            "ok": True,
            "command": "health",
            "data": result.model_dump(),
            "meta": {
                "view": container.config.runtime.default_view,
                "profile": container.profile_name,
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        response_formatter.emit_error("health", "DB_MIGRATION_FAILED", str(exc))


@app.command(name="config")
def config_command(
    action: Annotated[str, typer.Argument(..., help="get, set, or init")],
    section: Annotated[str | None, typer.Option("--section")] = None,
    key: Annotated[str | None, typer.Option("--key")] = None,
    value: Annotated[str | None, typer.Option("--value")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        match action:
            case "get":
                _handle_config_get(container, profile=profile)
            case "set":
                _handle_config_set(
                    container,
                    section=section,
                    key=key,
                    value=value,
                    profile=profile,
                )
            case "init":
                _handle_config_init(container, force=force)
            case _:
                response_formatter.emit_error("config", "INVALID_ARGS", "config action must be 'get', 'set', or 'init'")
    except ValueError as exc:
        response_formatter.emit_error("config", "INVALID_ARGS", str(exc))
    except FileExistsError as exc:
        response_formatter.emit_error("config", "CONFIG_EXISTS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("config", "DB_MIGRATION_FAILED", str(exc))


def _handle_config_get(container: Any, profile: str | None = None) -> None:
    result = container.config_service.get(profile=profile)
    typer.echo(
        json.dumps(response_formatter.format_config("config.get", result, container), ensure_ascii=False, indent=2)
    )


def _handle_config_set(
    container: Any,
    section: str | None,
    key: str | None,
    value: str | None,
    profile: str | None = None,
) -> None:
    if section is None or key is None or value is None:
        response_formatter.emit_error("config", "INVALID_ARGS", "config set requires --section, --key, and --value")
    result = container.config_service.set(
        section=section,
        key=key,
        value=value,
        profile=profile,
    )
    typer.echo(
        json.dumps(response_formatter.format_config("config.set", result, container), ensure_ascii=False, indent=2)
    )


def _handle_config_init(container: Any, force: bool = False) -> None:
    result = container.config_service.init(force=force)
    typer.echo(
        json.dumps(
            {
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
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="db")
def db_command(
    action: Annotated[str, typer.Argument(..., help="migrate or compact")],
    retention_days: Annotated[int, typer.Option("--retention-days")] = 30,
    rebuild_search_indexes: Annotated[
        bool, typer.Option("--rebuild-search-indexes/--no-rebuild-search-indexes")
    ] = True,
    vacuum: Annotated[bool, typer.Option("--vacuum/--no-vacuum")] = True,
    checkpoint: Annotated[bool, typer.Option("--checkpoint/--no-checkpoint")] = True,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile, auto_migrate=False)
        match action:
            case "migrate":
                _handle_db_migrate(container)
            case "compact":
                _handle_db_compact(
                    container,
                    retention_days=retention_days,
                    rebuild_search_indexes=rebuild_search_indexes,
                    vacuum=vacuum,
                    checkpoint=checkpoint,
                )
            case _:
                response_formatter.emit_error("db", "INVALID_ARGS", "db action must be 'migrate' or 'compact'")
    except typer.Exit:
        raise
    except ValueError as exc:
        response_formatter.emit_error("db", "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error("db", "DB_MIGRATION_FAILED", str(exc))


@app.command(name="mcp")
def mcp_command() -> None:
    run_stdio()


def _handle_db_migrate(container: Any) -> None:
    result = container.migration_service.migrate()
    checkpoint = container.maintenance_service.checkpoint_wal()
    payload = {
        "ok": True,
        "command": "db.migrate",
        "data": {
            "database_path": result.database_path,
            "applied": result.applied,
            "current_version": result.current_version,
            "applied_versions": result.applied_versions,
            "checkpoint": checkpoint,
        },
        "meta": {
            "view": container.config.runtime.default_view,
            "profile": container.profile_name,
        },
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _handle_db_compact(
    container: Any,
    *,
    retention_days: int,
    rebuild_search_indexes: bool,
    vacuum: bool,
    checkpoint: bool,
) -> None:
    if retention_days < 0:
        raise ValueError("retention_days must be greater than or equal to zero")
    deleted_before = None
    if retention_days > 0:
        from datetime import UTC, datetime, timedelta

        deleted_before = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    result = container.maintenance_service.compact(
        deleted_before=deleted_before,
        rebuild_indexes=rebuild_search_indexes,
        vacuum=vacuum,
        checkpoint=checkpoint,
    )
    payload = {
        "ok": True,
        "command": "db.compact",
        "data": result.model_dump(),
        "meta": {
            "view": container.config.runtime.default_view,
            "profile": container.profile_name,
        },
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
