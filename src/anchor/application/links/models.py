from __future__ import annotations

from pydantic import BaseModel


class DocumentLinkRecord(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    created_at: str


class DocumentLinkListResult(BaseModel):
    count: int
    links: list[DocumentLinkRecord]
