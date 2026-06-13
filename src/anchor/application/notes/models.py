from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class NoteRecord(BaseModel):
    id: str
    project: str
    metatags: dict[str, Any]
    title: str
    body: str
    source: str
    source_ref: str
    note_kind: str
    pinned: bool
    archived_at: str | None
    created_at: str
    updated_at: str


class NoteListItem(BaseModel):
    id: str
    project: str
    title: str
    pinned: bool
    created_at: str


class NotesSearchHit(BaseModel):
    note: NoteRecord
    chunk_id: str
    score: float
    snippet: str


class NotesSearchCandidate(BaseModel):
    note: NoteRecord
    chunk_id: str
    snippet: str
    token_count: int
    lexical_score: float = 0.0
    vector_score: float | None = None
    rerank_score: float | None = None


class NotesListResult(BaseModel):
    count: int
    notes: list[NoteListItem]


class NotesSearchResult(BaseModel):
    query: str
    count: int
    results: list[NotesSearchHit]
