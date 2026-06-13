from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


class FileListItem(BaseModel):
    id: str
    path: str
    root_path: str
    language: str
    file_size: int


class FileSearchHit(BaseModel):
    file: FileListItem
    chunk_id: str
    score: float
    snippet: str


class FilesIndexResult(BaseModel):
    count: int
    indexed: int
    skipped: int
    deleted: int


class FilesSearchResult(BaseModel):
    query: str
    count: int
    results: list[FileSearchHit]
