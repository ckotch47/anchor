from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from anchor.application.config_service import ConfigResult
from anchor.application.notes_service import NotesListResult
from anchor.container import build_container

app = typer.Typer(add_completion=False, help="Qatoria Anchor")
notes_app = typer.Typer(add_completion=False, help="Notes commands")
app.add_typer(notes_app, name="notes")


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
        _emit_error("health", "DB_MIGRATION_FAILED", str(exc))


@app.command(name="config")
def config_command(
    action: Annotated[str, typer.Argument(..., help="get or set")],
    section: Annotated[str | None, typer.Option("--section")] = None,
    key: Annotated[str | None, typer.Option("--key")] = None,
    value: Annotated[str | None, typer.Option("--value")] = None,
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
            case _:
                _emit_error("config", "INVALID_ARGS", "config action must be 'get' or 'set'")
    except ValueError as exc:
        _emit_error("config", "INVALID_ARGS", str(exc))
    except Exception as exc:
        _emit_error("config", "DB_MIGRATION_FAILED", str(exc))


def _handle_config_get(container: Any, profile: str | None = None) -> None:
    result = container.config_service.get(profile=profile)
    typer.echo(json.dumps(_config_payload("config.get", result, container), ensure_ascii=False, indent=2))


def _handle_config_set(
    container: Any,
    section: str | None,
    key: str | None,
    value: str | None,
    profile: str | None = None,
) -> None:
    if section is None or key is None or value is None:
        _emit_error("config", "INVALID_ARGS", "config set requires --section, --key, and --value")
    result = container.config_service.set(
        section=section,
        key=key,
        value=value,
        profile=profile,
    )
    typer.echo(json.dumps(_config_payload("config.set", result, container), ensure_ascii=False, indent=2))


def _config_payload(command: str, result: ConfigResult, container: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "data": {
            "config": result.config.model_dump(),
            "config_path": result.config_path,
            "profile_name": result.profile_name,
        },
        "meta": {
            "view": result.config.runtime.default_view,
            "profile": result.profile_name or container.profile_name,
        },
    }


def _emit_error(command: str, code: str, message: str) -> None:
    payload = {
        "ok": False,
        "command": command,
        "error": {
            "code": code,
            "message": message,
            "retryable": False,
        },
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    raise typer.Exit(code=1)


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
                _emit_error("db", "INVALID_ARGS", "db action must be 'migrate'")
    except typer.Exit:
        raise
    except Exception as exc:
        _emit_error("db", "DB_MIGRATION_FAILED", str(exc))


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


@notes_app.command(name="add")
def notes_add(
    title: Annotated[str, typer.Option("--title")],
    body: Annotated[str, typer.Option("--body")],
    source: Annotated[str, typer.Option("--source")] = "cli",
    source_ref: Annotated[str, typer.Option("--source-ref")] = "",
    pinned: Annotated[bool, typer.Option("--pinned")] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result = container.notes_service.add(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
        )
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "command": "notes.add",
                    "data": {"note": result.model_dump()},
                    "meta": {
                        "view": container.config.runtime.default_view,
                        "profile": container.profile_name,
                        "config_path": container.config_path,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        _emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        _emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="list")
def notes_list(
    limit: Annotated[int, typer.Option("--limit")] = 20,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result: NotesListResult = container.notes_service.list(limit=limit)
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "command": "notes.list",
                    "data": {"count": result.count, "notes": [note.model_dump() for note in result.notes]},
                    "meta": {
                        "view": container.config.runtime.default_view,
                        "profile": container.profile_name,
                        "config_path": container.config_path,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        _emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        _emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="get")
def notes_get(
    note_id: Annotated[str, typer.Option("--id")],
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result = container.notes_service.get(note_id)
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "command": "notes.get",
                    "data": {"note": result.model_dump()},
                    "meta": {
                        "view": container.config.runtime.default_view,
                        "profile": container.profile_name,
                        "config_path": container.config_path,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except LookupError as exc:
        _emit_error("notes", "NOT_FOUND", str(exc))
    except ValueError as exc:
        _emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        _emit_error("notes", "DB_MIGRATION_FAILED", str(exc))


@notes_app.command(name="search")
def notes_search(
    query: Annotated[str, typer.Option("--query")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    try:
        container = build_container(profile=profile)
        result = container.notes_service.search(query=query, limit=limit)
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "command": "notes.search",
                    "data": {
                        "query": result.query,
                        "count": result.count,
                        "results": [hit.model_dump() for hit in result.results],
                    },
                    "meta": {
                        "view": container.config.runtime.default_view,
                        "profile": container.profile_name,
                        "config_path": container.config_path,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except ValueError as exc:
        _emit_error("notes", "INVALID_ARGS", str(exc))
    except Exception as exc:
        _emit_error("notes", "DB_MIGRATION_FAILED", str(exc))
