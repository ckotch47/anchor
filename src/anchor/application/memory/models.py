from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MemoryScope = Literal["chat", "project", "global"]
MemoryScopeFilter = Literal["all", "chat", "project", "global"]
MemoryFactStatus = Literal["candidate", "active", "superseded", "conflicted", "deleted"]


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class MemoryFactCreate(BaseModel):
    scope: MemoryScope
    project: str | None = None
    source_chat_id: str | None = None
    fact_type: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: MemoryFactStatus = "candidate"
    evidence_refs: list[str | dict[str, Any]] = Field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes_id: str | None = None

    _normalize_fact_type = field_validator("fact_type")(
        lambda value: _require_text(value, "fact_type")
    )
    _normalize_content = field_validator("content")(
        lambda value: _require_text(value, "content")
    )

    @field_validator("project", "source_chat_id", "valid_from", "valid_until", "supersedes_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return None if value is None else _require_text(value, "value")

    @model_validator(mode="after")
    def _validate_validity_window(self) -> MemoryFactCreate:
        if self.valid_from is not None and self.valid_until is not None and self.valid_from > self.valid_until:
            raise ValueError("valid_from must not be later than valid_until")
        return self


class MemoryFact(BaseModel):
    id: str
    scope: MemoryScope
    project: str | None
    source_chat_id: str | None
    fact_type: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: MemoryFactStatus
    evidence_refs: list[str | dict[str, Any]] = Field(default_factory=list)
    valid_from: str | None
    valid_until: str | None
    supersedes_id: str | None
    created_at: str
    updated_at: str


class MemoryFactStatusUpdate(BaseModel):
    status: MemoryFactStatus


class MemorySearchRequest(BaseModel):
    query: str
    scope: MemoryScopeFilter = "all"
    project: str | None = None
    projects: list[str] | None = None
    chat_id: str | None = None
    fact_type: str | None = None
    status: MemoryFactStatus | list[MemoryFactStatus] | None = "active"
    limit: int = Field(default=20, gt=0)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        return _require_text(value, "query")

    @field_validator("project", "chat_id", "fact_type")
    @classmethod
    def _normalize_filters(cls, value: str | None) -> str | None:
        return None if value is None else _require_text(value, "filter")

    @field_validator("projects")
    @classmethod
    def _normalize_projects(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [_require_text(project, "project") for project in value]
        if not normalized:
            raise ValueError("projects must not be empty")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def _validate_project_filters(self) -> MemorySearchRequest:
        if self.project is not None and self.projects is not None:
            raise ValueError("project and projects are mutually exclusive")
        return self


class MemorySearchHit(BaseModel):
    fact: MemoryFact
    score: float
    snippet: str


class MemorySearchResult(BaseModel):
    query: str
    count: int
    results: list[MemorySearchHit]


class MemoryContextResult(BaseModel):
    query: str
    project: str
    chat_id: str | None
    count: int
    scenario_count: int
    budget_tokens: int
    context: str
    scenarios: list[dict[str, Any]]
    results: list[MemorySearchHit]


class MemoryEvidenceItem(BaseModel):
    reference: str | dict[str, Any]
    found: bool
    record: dict[str, Any] | None = None


class MemoryEvidenceResult(BaseModel):
    fact_id: str
    project: str
    count: int
    evidence: list[MemoryEvidenceItem]


class MemoryScenario(BaseModel):
    id: str
    scope: Literal["project", "global"]
    project: str | None
    title: str
    summary: str
    fact_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str | dict[str, Any]] = Field(default_factory=list)
    status: Literal["active", "superseded", "deleted"]
    created_at: str
    updated_at: str


class MemoryScenarioSearchHit(BaseModel):
    scenario: MemoryScenario
    score: float
    snippet: str


class MemoryScenarioSearchResult(BaseModel):
    query: str
    count: int
    results: list[MemoryScenarioSearchHit]


class MemoryConflictGroup(BaseModel):
    scope: MemoryScope
    project: str | None
    chat_id: str | None
    fact_type: str
    facts: list[MemoryFact]


class MemoryConflictResult(BaseModel):
    count: int
    groups: list[MemoryConflictGroup]


class MemoryMetricsResult(BaseModel):
    project: str
    facts_by_status: dict[str, int]
    scenarios_by_status: dict[str, int]
    conflicted_facts: int
    total_evidence_refs: int
    broken_evidence_refs: int
    broken_canonical_evidence_refs: int
    external_evidence_refs: int
    pending_extraction_count: int
    checkpoints: dict[str, int]


class MemoryPipelineResult(BaseModel):
    project: str
    chat_id: str | None
    processed_history: int
    extracted_facts: int
    scenario: MemoryScenario | None = None
    checkpoint_status: str
