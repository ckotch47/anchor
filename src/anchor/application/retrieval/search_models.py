from __future__ import annotations

from pydantic import BaseModel

from anchor.application.notes.models import NoteRecord


class NotesSearchCandidate(BaseModel):
    note: NoteRecord
    chunk_id: str
    snippet: str
    token_count: int
    lexical_score: float = 0.0
    vector_score: float | None = None
    rerank_score: float | None = None
