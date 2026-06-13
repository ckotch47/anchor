from __future__ import annotations

import json
from typing import Any

import typer

from anchor.application.system.config_service import ConfigResult


def emit_error(command: str, code: str, message: str) -> None:
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


def config_payload(command: str, result: ConfigResult, container: Any) -> dict[str, Any]:
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


def build_success_payload(
    command: str,
    data: dict[str, Any],
    container: Any,
    *,
    include_config_path: bool = True,
    profile: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "view": container.config.runtime.default_view,
        "profile": profile or container.profile_name,
    }
    if include_config_path:
        meta["config_path"] = str(container.config_path)
    if extra_meta:
        meta.update(extra_meta)
    return {
        "ok": True,
        "command": command,
        "data": data,
        "meta": meta,
    }


def parse_metatags(raw_value: str | None) -> dict[str, object]:
    if raw_value is None or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("metatags must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("metatags must be a JSON object")
    return parsed


def resolve_project(container: Any, project: str | None) -> str:
    if project is None or not project.strip():
        return container.config.runtime.default_project
    return project
