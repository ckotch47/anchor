from __future__ import annotations

from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.application.document_chunking import DocumentChunkingService
from anchor.application.embedding_service import EmbeddingService
from anchor.application.notes_models import NoteRecord, NotesListResult, NotesSearchResult


class NotesService:
    def __init__(
        self,
        repository: SqliteNotesRepository,
        chunking_service: DocumentChunkingService,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._repository = repository
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service

    def add(
        self,
        *,
        title: str,
        body: str,
        source: str = "cli",
        source_ref: str = "",
        pinned: bool = False,
    ) -> NoteRecord:
        self._require_non_empty(title, "title")
        self._require_non_empty(body, "body")
        chunks = self._chunking_service.chunk_note(title=title, body=body)
        result = self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            chunks=chunks,
        )
        self._materialize_embeddings(result.id)
        return result

    def list(self, limit: int = 20) -> NotesListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        notes = self._repository.list(limit)
        return NotesListResult(count=len(notes), notes=notes)

    def get(self, note_id: str) -> NoteRecord:
        self._require_non_empty(note_id, "id")
        note = self._repository.get(note_id)
        if note is None:
            raise LookupError(f"note not found: {note_id}")
        return note

    def search(self, query: str, limit: int = 20) -> NotesSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        results = self._repository.search(query=query, limit=limit)
        return NotesSearchResult(query=query, count=len(results), results=results)

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

    def _materialize_embeddings(self, document_id: str) -> None:
        if self._embedding_service is None:
            return
        chunks = self._repository.list_chunks(document_id)
        if not chunks:
            return
        try:
            result = self._embedding_service.embed_chunks(
                [chunk.id for chunk in chunks],
                [chunk.chunk_text for chunk in chunks],
            )
            self._repository.store_chunk_embeddings(
                result.embeddings,
                created_at=chunks[0].created_at,
            )
        except Exception:
            return
