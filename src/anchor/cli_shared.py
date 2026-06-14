from __future__ import annotations

import json
from typing import Any

import typer

from anchor.application.system.config_service import ConfigResult


class ResponseEnvelopeFormatter:
    def emit_error(self, command: str, code: str, message: str) -> None:
        typer.echo(json.dumps(self.format_error(command, code, message), ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    def format_error(self, command: str, code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            },
        }

    def format_config(self, command: str, result: ConfigResult, container: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "view": result.config.runtime.default_view,
        }
        if result.config.runtime.default_view == "full":
            resolved_profile = result.profile_name or container.profile_name
            if resolved_profile is not None:
                meta["profile"] = resolved_profile
        return {
            "ok": True,
            "command": command,
            "data": {
                "config": result.config.model_dump(),
                "config_path": result.config_path,
                "profile_name": result.profile_name,
            },
            "meta": meta,
        }

    def format_success(
        self,
        command: str,
        data: dict[str, Any],
        container: Any,
        *,
        view: str | None = None,
        include_config_path: bool | None = None,
        profile: str | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_view = resolve_view(container, view)
        meta: dict[str, Any] = {
            "view": resolved_view,
        }
        if resolved_view == "full":
            if include_config_path is None:
                include_config_path = True
            resolved_profile = profile or container.profile_name
            if resolved_profile is not None:
                meta["profile"] = resolved_profile
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

    def format_search(
        self,
        command: str,
        result: Any,
        container: Any,
        *,
        view: str | None = None,
        profile: str | None = None,
        project: str | None = None,
        projects: list[str] | None = None,
        types: list[str] | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        resolved_view = resolve_view(container, view)
        data = result.model_dump(exclude_none=True)
        if resolved_view == "compact":
            data.pop("query", None)
            for hit in data.get("results", []):
                if isinstance(hit, dict):
                    hit.pop("attributes", None)
        if not explain:
            data.pop("stats", None)
        meta: dict[str, Any] = {
            "view": resolved_view,
        }
        if resolved_view == "full":
            resolved_profile = profile or container.profile_name
            if resolved_profile is not None:
                meta["profile"] = resolved_profile
            if project is not None:
                meta["project"] = project
            meta["config_path"] = str(container.config_path)
            if projects is not None:
                meta["projects"] = projects
            if types is not None:
                meta["types"] = types
            if explain:
                meta["explain"] = explain
        return {
            "ok": True,
            "command": command,
            "data": data,
            "meta": meta,
        }


response_formatter = ResponseEnvelopeFormatter()


def resolve_view(container: Any, view: str | None) -> str:
    if view is None or not view.strip():
        return container.config.runtime.default_view
    normalized = view.strip().lower()
    if normalized not in {"compact", "full"}:
        raise ValueError("view must be 'compact' or 'full'")
    return normalized


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
