from __future__ import annotations

from pydantic import BaseModel


class NoteRecord(BaseModel):
    id: str
    title: str
    body: str
    source: str
    source_ref: str
    note_kind: str
    pinned: bool
    archived_at: str | None
    created_at: str
    updated_at: str


class NotesSearchHit(BaseModel):
    note: NoteRecord
    chunk_id: str
    score: float
    snippet: str


class NotesListResult(BaseModel):
    count: int
    notes: list[NoteRecord]


class NotesSearchResult(BaseModel):
    query: str
    count: int
    results: list[NotesSearchHit]
