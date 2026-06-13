from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from anchor.cli_notes import notes_add, notes_app, notes_get, notes_list, notes_search, notes_update
from anchor.cli_shared import config_payload, emit_error
from anchor.cli_tasks import tasks_add, tasks_app, tasks_done, tasks_list, tasks_search, tasks_update
from anchor.container import build_container

app = typer.Typer(add_completion=False, help="Qatoria Anchor")
app.add_typer(notes_app, name="notes")
app.add_typer(tasks_app, name="tasks")

__all__ = [
    "app",
    "config_command",
    "db_command",
    "health",
    "notes_add",
    "notes_get",
    "notes_list",
    "notes_search",
    "notes_update",
    "tasks_add",
    "tasks_done",
    "tasks_list",
    "tasks_search",
    "tasks_update",
]


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
                "config_path": str(container.config_path),
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        emit_error("health", "DB_MIGRATION_FAILED", str(exc))


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
                emit_error("config", "INVALID_ARGS", "config action must be 'get', 'set', or 'init'")
    except ValueError as exc:
        emit_error("config", "INVALID_ARGS", str(exc))
    except FileExistsError as exc:
        emit_error("config", "CONFIG_EXISTS", str(exc))
    except Exception as exc:
        emit_error("config", "DB_MIGRATION_FAILED", str(exc))


def _handle_config_get(container: Any, profile: str | None = None) -> None:
    result = container.config_service.get(profile=profile)
    typer.echo(json.dumps(config_payload("config.get", result, container), ensure_ascii=False, indent=2))


def _handle_config_set(
    container: Any,
    section: str | None,
    key: str | None,
    value: str | None,
    profile: str | None = None,
) -> None:
    if section is None or key is None or value is None:
        emit_error("config", "INVALID_ARGS", "config set requires --section, --key, and --value")
    result = container.config_service.set(
        section=section,
        key=key,
        value=value,
        profile=profile,
    )
    typer.echo(json.dumps(config_payload("config.set", result, container), ensure_ascii=False, indent=2))


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
    action: Annotated[str, typer.Argument(..., help="migrate")],
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile, auto_migrate=False)
        match action:
            case "migrate":
                _handle_db_migrate(container)
            case _:
                emit_error("db", "INVALID_ARGS", "db action must be 'migrate'")
    except typer.Exit:
        raise
    except Exception as exc:
        emit_error("db", "DB_MIGRATION_FAILED", str(exc))


def _handle_db_migrate(container: Any) -> None:
    result = container.migration_service.migrate()
    payload = {
        "ok": True,
        "command": "db.migrate",
        "data": {
            "database_path": result.database_path,
            "applied": result.applied,
            "current_version": result.current_version,
            "applied_versions": result.applied_versions,
        },
        "meta": {
            "view": container.config.runtime.default_view,
            "profile": container.profile_name,
        },
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
