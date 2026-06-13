from __future__ import annotations

from pydantic import BaseModel


class DocumentChunkRecord(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    token_count: int
    created_at: str


class ChunkEmbeddingRecord(BaseModel):
    chunk_id: str
    model: str
    embedding: list[float]
