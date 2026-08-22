from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_ALLOWED_SEARCH_TYPES = {"notes", "tasks", "history", "files"}
MAX_RETRIEVAL_LIMIT = 100


class SearchQuery(BaseModel):
    query: str
    types: list[str] = Field(default_factory=lambda: ["notes", "tasks", "history", "files"])
    project: str
    projects: list[str] | None = None
    limit: int = Field(default=20, gt=0, le=MAX_RETRIEVAL_LIMIT)
    budget_tokens: int = Field(default=800, gt=0, le=10_000)
    weights: dict[str, float] = Field(default_factory=dict)
    explain: bool = False
    cursor: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> SearchQuery:
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("query must not be empty")
        self.project = self.project.strip()
        if not self.project:
            raise ValueError("project must not be empty")
        if self.projects is not None:
            self.projects = _normalize_projects(self.projects)
        if self.cursor is not None and not self.cursor.strip():
            self.cursor = None
        self.types = _normalize_search_types(self.types)
        if self.weights:
            normalized_weights: dict[str, float] = {}
            for raw_type, raw_weight in self.weights.items():
                normalized_type = raw_type.strip().lower()
                if normalized_type not in _ALLOWED_SEARCH_TYPES:
                    raise ValueError(f"unsupported search type in weights: {raw_type}")
                if raw_weight <= 0:
                    raise ValueError("search weights must be greater than zero")
                normalized_weights[normalized_type] = float(raw_weight)
            self.weights = normalized_weights
        return self


def validate_retrieval_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if not 0 < limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")
    return limit


def normalize_fts5_query(raw_query: str) -> str:
    tokens = _TOKEN_PATTERN.findall(raw_query)
    if not tokens:
        raise ValueError("query must not be empty")
    return " AND ".join(f'"{t}"' for t in tokens)


def _normalize_search_types(raw_types: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_type in raw_types:
        normalized_type = raw_type.strip().lower()
        if not normalized_type:
            continue
        if normalized_type not in _ALLOWED_SEARCH_TYPES:
            raise ValueError(f"unsupported search type: {raw_type}")
        if normalized_type not in normalized:
            normalized.append(normalized_type)
    if not normalized:
        raise ValueError("types must not be empty")
    return normalized


def _normalize_projects(raw_projects: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_project in raw_projects:
        normalized_project = raw_project.strip()
        if not normalized_project:
            continue
        if normalized_project not in normalized:
            normalized.append(normalized_project)
    if not normalized:
        raise ValueError("projects must not be empty")
    return normalized
