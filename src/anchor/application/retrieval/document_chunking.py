from __future__ import annotations

import re

from pydantic import BaseModel


class DocumentChunkDraft(BaseModel):
    chunk_index: int
    chunk_text: str
    token_count: int


class DocumentChunkingService:
    def chunk_note(self, *, title: str, body: str) -> list[DocumentChunkDraft]:
        del title
        body = body.strip()
        if not body:
            return []
        return [DocumentChunkDraft(chunk_index=0, chunk_text=body, token_count=count_tokens(body))]


def count_tokens(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", text, flags=re.UNICODE))
