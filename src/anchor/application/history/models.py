from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HistoryRecord(BaseModel):
    id: str
    project: str
    metatags: dict[str, Any]
    entry_type: str
    actor: str
    payload: str
    correlation_id: str
    created_at: str
    updated_at: str


class HistoryListItem(BaseModel):
    id: str
    project: str
    entry_type: str
    actor: str
    correlation_id: str
    created_at: str


class HistorySearchHit(BaseModel):
    history: HistoryListItem
    chunk_id: str
    score: float
    snippet: str


class HistorySearchCandidate(BaseModel):
    history: HistoryListItem
    chunk_id: str
    snippet: str
    token_count: int
    lexical_score: float = 0.0
    vector_score: float | None = None
    rerank_score: float | None = None


class HistoryAppendResult(BaseModel):
    history: HistoryRecord


class HistorySearchResult(BaseModel):
    query: str
    count: int
    results: list[HistorySearchHit]
