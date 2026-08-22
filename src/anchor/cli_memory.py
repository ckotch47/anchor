from __future__ import annotations

import json
from typing import Annotated, Any, cast

import typer

from anchor.application.memory.models import MemoryFactStatus, MemoryScope, MemoryScopeFilter
from anchor.cli_shared import resolve_project, response_formatter
from anchor.container import build_container

memory_app = typer.Typer(add_completion=False, help="Hierarchical memory commands")


@memory_app.command(name="extract")
def memory_extract(
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.extract"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.extract(
            project=resolve_project(container, project),
            chat_id=chat_id,
            limit=limit,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except RuntimeError as exc:
        response_formatter.emit_error(command, "PROVIDER_OFFLINE", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "PROVIDER_ERROR", str(exc))


@memory_app.command(name="flush")
def memory_flush(
    project: Annotated[str | None, typer.Option("--project")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.flush"
    try:
        container = build_container(profile=profile)
        resolved_project = resolve_project(container, project)
        if dry_run:
            data = {"dry_run": True, "preview": container.memory_service.preview_extraction(project=resolved_project)}
            typer.echo(json.dumps(response_formatter.format_success(command, data, container), ensure_ascii=False, indent=2))
            return
        result = container.history_service.flush_memory_extraction(project=resolved_project)
        data = {"flushed": result is not None}
        if result is not None and hasattr(result, "model_dump"):
            data["extraction"] = result.model_dump()
        typer.echo(json.dumps(response_formatter.format_success(command, data, container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "PROVIDER_ERROR", str(exc))


def _parse_evidence_refs(value: str | None) -> list[str | dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("evidence_refs must be a JSON array") from exc
    if not isinstance(parsed, list):
        raise ValueError("evidence_refs must be a JSON array")
    return parsed


@memory_app.command(name="capture")
def memory_capture(
    content: Annotated[str, typer.Option("--content")],
    fact_type: Annotated[str, typer.Option("--fact-type")],
    scope: Annotated[str, typer.Option("--scope")] = "project",
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    confidence: Annotated[float, typer.Option("--confidence")] = 1.0,
    evidence_refs: Annotated[str | None, typer.Option("--evidence-refs")] = None,
    status: Annotated[str, typer.Option("--status")] = "candidate",
    supersedes_id: Annotated[str | None, typer.Option("--supersedes-id")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.capture"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.capture(
            content=content,
            fact_type=fact_type,
            scope=cast(MemoryScope, scope),
            project=resolve_project(container, project),
            chat_id=chat_id,
            confidence=confidence,
            evidence_refs=_parse_evidence_refs(evidence_refs),
            status=cast(MemoryFactStatus, status),
            supersedes_id=supersedes_id,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, {"fact": result.model_dump()}, container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except LookupError as exc:
        response_formatter.emit_error(command, "NOT_FOUND", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="search")
def memory_search(
    query: Annotated[str, typer.Option("--query")],
    scope: Annotated[str, typer.Option("--scope")] = "all",
    project: Annotated[str | None, typer.Option("--project")] = None,
    projects: Annotated[list[str] | None, typer.Option("--projects")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    fact_type: Annotated[str | None, typer.Option("--fact-type")] = None,
    status: Annotated[list[str] | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.search"
    try:
        if project is not None and projects is not None:
            raise ValueError("use either --project or repeated --projects, not both")
        container = build_container(profile=profile)
        result = container.memory_service.search(
            query=query,
            scope=cast(MemoryScopeFilter, scope),
            project=resolve_project(container, project) if project else None,
            projects=projects,
            chat_id=chat_id,
            fact_type=fact_type,
            status=cast(list[MemoryFactStatus] | None, status),
            limit=limit,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="recall")
def memory_recall(
    query: Annotated[str, typer.Option("--query")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 5,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.recall"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.recall(
            query=query,
            project=resolve_project(container, project),
            chat_id=chat_id,
            limit=limit,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="context")
def memory_context(
    query: Annotated[str, typer.Option("--query")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 5,
    budget_tokens: Annotated[int | None, typer.Option("--budget-tokens")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.context"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.build_context(
            query=query,
            project=resolve_project(container, project),
            chat_id=chat_id,
            limit=limit,
            budget_tokens=budget_tokens,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="promote")
def memory_promote(
    fact_id: Annotated[str, typer.Option("--id")],
    scope: Annotated[str, typer.Option("--scope")],
    source_project: Annotated[str | None, typer.Option("--source-project")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.promote"
    try:
        if source_project is None or not source_project.strip():
            raise ValueError("memory promote requires --source-project")
        container = build_container(profile=profile)
        result = container.memory_service.promote(
            fact_id,
            scope=cast(MemoryScope, scope),
            source_project=source_project,
            project=project,
            chat_id=chat_id,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, {"fact": result.model_dump()}, container), ensure_ascii=False, indent=2))
    except LookupError as exc:
        response_formatter.emit_error(command, "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="scenarios")
def memory_scenarios(
    query: Annotated[str, typer.Option("--query")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 5,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.scenarios"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.search_scenarios(
            query=query,
            project=resolve_project(container, project),
            limit=limit,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="conflicts")
def memory_conflicts(
    project: Annotated[str | None, typer.Option("--project")] = None,
    chat_id: Annotated[str | None, typer.Option("--chat-id")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.conflicts"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.conflicts(
            project=resolve_project(container, project),
            chat_id=chat_id,
            limit=limit,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="metrics")
def memory_metrics(
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.metrics"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.metrics(project=resolve_project(container, project))
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="evidence")
def memory_evidence(
    fact_id: Annotated[str, typer.Option("--id")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.evidence"
    try:
        container = build_container(profile=profile)
        result = container.memory_service.evidence(fact_id, project=resolve_project(container, project))
        typer.echo(json.dumps(response_formatter.format_success(command, result.model_dump(), container), ensure_ascii=False, indent=2))
    except LookupError as exc:
        response_formatter.emit_error(command, "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))


@memory_app.command(name="status")
def memory_status(
    fact_id: Annotated[str, typer.Option("--id")],
    status: Annotated[str, typer.Option("--status")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
) -> None:
    command = "memory.status"
    try:
        if project is None or not project.strip():
            raise ValueError("memory status requires --project")
        container = build_container(profile=profile)
        result = container.memory_service.update_status(
            fact_id,
            cast(MemoryFactStatus, status),
            project=project,
        )
        typer.echo(json.dumps(response_formatter.format_success(command, {"fact": result.model_dump()}, container), ensure_ascii=False, indent=2))
    except LookupError as exc:
        response_formatter.emit_error(command, "NOT_FOUND", str(exc))
    except ValueError as exc:
        response_formatter.emit_error(command, "INVALID_ARGS", str(exc))
    except Exception as exc:
        response_formatter.emit_error(command, "DB_MIGRATION_FAILED", str(exc))
