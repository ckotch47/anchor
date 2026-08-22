from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    required: bool
    type: str


@dataclass(frozen=True)
class OperationSpec:
    parameters: tuple[ParameterSpec, ...]
    scope: str = "project_required"
    transports: tuple[str, ...] = ("cli", "mcp")


def parameter(name: str, required: bool, parameter_type: str) -> ParameterSpec:
    return ParameterSpec(name=name, required=required, type=parameter_type)


OPERATION_REGISTRY: dict[str, dict[str, OperationSpec]] = {
    "links": {
        "add": OperationSpec((parameter("project", True, "string"), parameter("source_id", True, "string"), parameter("target_id", True, "string"), parameter("relation_type", True, "string"))),
        "list": OperationSpec((parameter("project", True, "string"), parameter("source_id", False, "string"), parameter("target_id", False, "string"))),
        "delete": OperationSpec((parameter("project", True, "string"), parameter("source_id", True, "string"), parameter("target_id", True, "string"), parameter("relation_type", True, "string"))),
    },
    "memory": {
        "promote": OperationSpec((parameter("fact_id", True, "string"), parameter("scope", True, "chat|project|global"), parameter("source_project", True, "string"), parameter("project", False, "string"), parameter("chat_id", False, "string"))),
        "status": OperationSpec((parameter("fact_id", True, "string"), parameter("status", True, "candidate|active|superseded|conflicted|deleted"), parameter("project", True, "string"))),
    },
    "tasks": {
        "add": OperationSpec((parameter("title", True, "string"), parameter("project", False, "string"), parameter("external_key", False, "string"), parameter("parent_document_id", False, "uuid7"), parameter("blocked_by_document_id", False, "uuid7")), scope="project_defaultable"),
        "update": OperationSpec((parameter("task_id", True, "uuid7"), parameter("project", False, "string"), parameter("due_at", False, "datetime"), parameter("parent_document_id", False, "uuid7"), parameter("blocked_by_document_id", False, "uuid7"), parameter("clear_due_at", False, "boolean"), parameter("clear_parent_document_id", False, "boolean"), parameter("clear_blocked_by_document_id", False, "boolean")), scope="project_defaultable"),
        "get_by_external_key": OperationSpec((parameter("external_key", True, "string"), parameter("project", True, "string"))),
        "upsert": OperationSpec((parameter("external_key", True, "string"), parameter("title", True, "string"), parameter("project", True, "string"), parameter("body", False, "string"), parameter("source", False, "string"), parameter("source_ref", False, "string"), parameter("metatags", False, "object"), parameter("task_kind", False, "string"), parameter("priority", False, "integer"), parameter("due_at", False, "datetime"), parameter("parent_document_id", False, "uuid7"), parameter("blocked_by_document_id", False, "uuid7"))),
        "status": OperationSpec((parameter("task_id", True, "uuid7"), parameter("status", True, "open|in_progress|blocked|done|closed"), parameter("project", True, "string"), parameter("blocked_reason", False, "string"))),
        "done": OperationSpec((parameter("task_id", True, "uuid7"), parameter("project", False, "string")), scope="project_defaultable"),
    },
}
