from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_ALLOWED_SEARCH_TYPES = {"notes", "tasks", "history", "files"}


class SearchQuery(BaseModel):
    query: str
    types: list[str] = Field(default_factory=lambda: ["notes", "tasks", "files"])
    project: str
    limit: int = 20
    budget_tokens: int = 800
    weights: dict[str, float] = Field(default_factory=dict)
    explain: bool = False

    @model_validator(mode="after")
    def _validate(self) -> SearchQuery:
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("query must not be empty")
        self.project = self.project.strip()
        if not self.project:
            raise ValueError("project must not be empty")
        if self.limit <= 0:
            raise ValueError("limit must be greater than zero")
        if self.budget_tokens <= 0:
            raise ValueError("budget_tokens must be greater than zero")
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


def normalize_fts5_query(raw_query: str) -> str:
    tokens = _TOKEN_PATTERN.findall(raw_query)
    if not tokens:
        raise ValueError("query must not be empty")
    return " AND ".join(tokens)


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
