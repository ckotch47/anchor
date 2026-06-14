from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from anchor.application.files.chunking import FileChunkDraft


@dataclass(frozen=True)
class FileIndexDraft:
    document_id: str
    project: str
    path: str
    root_path: str
    language: str
    metatags: dict[str, Any]
    file_size: int
    content_hash: str
    mtime_ns: int
    chunks: list[FileChunkDraft]


class IndexedFileRecord(BaseModel):
    id: str
    project: str
    metatags: dict[str, Any]
    path: str
    root_path: str
    language: str
    file_size: int
    content_hash: str
    mtime_ns: int
    created_at: str
    updated_at: str
    deleted_at: str | None


class FileChunkRecord(BaseModel):
    id: str
    document_id: str
    project: str
    path: str
    root_path: str
    language: str
    chunk_index: int
    start_line: int
    end_line: int
    chunk_text: str
    token_count: int
    created_at: str


class FileListItem(BaseModel):
    id: str
    path: str
    root_path: str
    language: str
    file_size: int


class FileSearchHit(BaseModel):
    file: IndexedFileRecord | FileListItem
    chunk_id: str
    score: float
    snippet: str


class FileSearchCandidate(BaseModel):
    file: FileListItem
    chunk_id: str
    snippet: str
    token_count: int
    lexical_score: float = 0.0
    vector_score: float | None = None
    rerank_score: float | None = None


class FilesIndexResult(BaseModel):
    count: int
    indexed: int
    skipped: int
    deleted: int


class FilesGetResult(BaseModel):
    file: IndexedFileRecord


class FilesListResult(BaseModel):
    count: int
    files: list[IndexedFileRecord | FileListItem]
    next_cursor: str | None = None


class FilesSearchResult(BaseModel):
    query: str
    count: int
    results: list[FileSearchHit]
    stats: dict[str, Any] | None = None
