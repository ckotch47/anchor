from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anchor.application.notes.models import NoteRecord
from anchor.application.retrieval.search_query import SearchQuery


class NotesSearchCandidate(BaseModel):
    note: NoteRecord
    chunk_id: str
    snippet: str
    token_count: int
    lexical_score: float = 0.0
    vector_score: float | None = None
    rerank_score: float | None = None


class SearchHit(BaseModel):
    entity_type: str
    entity_id: str
    project: str
    title: str
    score: float
    snippet: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class SearchStats(BaseModel):
    budget_tokens: int
    consumed_tokens: int
    candidate_counts: dict[str, int]
    deduplicated_count: int
    returned_count: int


class SearchResult(BaseModel):
    query: SearchQuery
    count: int
    results: list[SearchHit]
    next_cursor: str | None = None
    stats: SearchStats | None = None
