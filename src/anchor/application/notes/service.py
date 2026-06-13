from __future__ import annotations

import json
from collections import OrderedDict

from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.models import (
    NoteListItem,
    NoteRecord,
    NotesListResult,
    NotesSearchCandidate,
    NotesSearchHit,
    NotesSearchResult,
)
from anchor.application.retrieval.document_chunking import DocumentChunkingService, count_tokens
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_scoring import combine_search_scores


class NotesService:
    def __init__(
        self,
        repository: SqliteNotesRepository,
        chunking_service: DocumentChunkingService,
        project: str,
        embedding_service: EmbeddingService | None = None,
        rerank_service: RerankService | None = None,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._chunking_service = chunking_service
        self._project = project
        self._embedding_service = embedding_service
        self._rerank_service = rerank_service
        self._budget_tokens = budget_tokens

    def add(
        self,
        *,
        title: str,
        body: str,
        source: str = "cli",
        source_ref: str = "",
        pinned: bool = False,
        project: str | None = None,
        metatags: dict[str, object] | None = None,
    ) -> NoteRecord:
        self._require_non_empty(title, "title")
        self._require_non_empty(body, "body")
        resolved_project = project or self._project
        chunks = self._chunking_service.chunk_note(title=title, body=body)
        result = self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            project=resolved_project,
            metatags=metatags or {},
            chunks=chunks,
        )
        self._queue_embeddings(result.id)
        return result

    def update(
        self,
        note_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        pinned: bool | None = None,
        project: str | None = None,
        metatags: dict[str, object] | None = None,
    ) -> NoteRecord:
        self._require_non_empty(note_id, "id")
        if title is not None:
            self._require_non_empty(title, "title")
        if body is not None:
            self._require_non_empty(body, "body")
        if all(value is None for value in (title, body, source, source_ref, pinned, metatags)):
            raise ValueError("update requires at least one field")
        resolved_project = project or self._project
        chunks = None
        if title is not None or body is not None:
            current = self.get(note_id, project=resolved_project)
            updated_title = title if title is not None else current.title
            updated_body = body if body is not None else current.body
            chunks = self._chunking_service.chunk_note(title=updated_title, body=updated_body)
        result = self._repository.update(
            note_id,
            project=resolved_project,
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            metatags=metatags,
            chunks=chunks,
        )
        if result is None:
            raise LookupError(f"note not found: {note_id}")
        if chunks is not None:
            self._queue_embeddings(result.id)
        return result

    def list(self, limit: int = 20, *, project: str | None = None) -> NotesListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        notes = self._repository.list(limit, project=project or self._project)
        return NotesListResult(
            count=len(notes),
            notes=[
                NoteListItem(
                    id=note.id,
                    project=note.project,
                    title=note.title,
                    pinned=note.pinned,
                    created_at=note.created_at,
                )
                for note in notes
            ],
        )

    def get(self, note_id: str, *, project: str | None = None) -> NoteRecord:
        self._require_non_empty(note_id, "id")
        note = self._repository.get(note_id, project=project or self._project)
        if note is None:
            raise LookupError(f"note not found: {note_id}")
        return note

    def delete(self, note_id: str, *, project: str | None = None) -> NoteRecord:
        self._require_non_empty(note_id, "id")
        deleted = self._repository.delete(note_id, project=project or self._project)
        if deleted is None:
            raise LookupError(f"note not found: {note_id}")
        return deleted

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> NotesSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        resolved_project = project or self._project
        self._drain_pending_embeddings(resolved_project)
        candidate_limit = max(limit * 4, limit)
        candidates = self._collect_candidates(query, candidate_limit, resolved_project)
        reranked_candidates = self._rerank_candidates(query, candidates)
        deduplicated = self._deduplicate_by_note(reranked_candidates)
        trimmed = self._trim_to_budget(
            deduplicated,
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        results = [
            NotesSearchHit(
                note=candidate.note,
                chunk_id=candidate.chunk_id,
                score=combine_search_scores(
                    lexical_score=candidate.lexical_score,
                    vector_score=candidate.vector_score,
                    rerank_score=candidate.rerank_score,
                ),
                snippet=candidate.snippet,
            )
            for candidate in trimmed[:limit]
        ]
        return NotesSearchResult(query=query, count=len(results), results=results)

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

    def _queue_embeddings(self, document_id: str) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "enqueue_embedding_index"):
            return
        try:
            self._repository.enqueue_embedding_index(document_id)
        except Exception:
            return

    def _drain_pending_embeddings(self, project: str) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "pending_embedding_documents"):
            return
        try:
            pending_documents = self._repository.pending_embedding_documents(project=project)
        except Exception:
            return
        for document_id in pending_documents:
            try:
                chunks = self._repository.list_chunks(document_id)
                if not chunks:
                    if hasattr(self._repository, "mark_embedding_index_ready"):
                        self._repository.mark_embedding_index_ready(document_id)
                    continue
                result = self._embedding_service.embed_chunks(
                    [chunk.id for chunk in chunks],
                    [chunk.chunk_text for chunk in chunks],
                )
                self._repository.store_chunk_embeddings(
                    result.embeddings,
                    project=chunks[0].project,
                    metatags=self._serialize_metatags(chunks[0].metatags),
                    created_at=chunks[0].created_at,
                )
                if hasattr(self._repository, "mark_embedding_index_ready"):
                    self._repository.mark_embedding_index_ready(document_id)
            except Exception as exc:
                if hasattr(self._repository, "mark_embedding_index_error"):
                    self._repository.mark_embedding_index_error(document_id, last_error=str(exc))

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, separators=(",", ":"), ensure_ascii=False)

    def _collect_candidates(
        self,
        query: str,
        limit: int,
        project: str,
    ) -> list[NotesSearchCandidate]:
        lexical_rows = self._search_lexical_candidates(query, limit, project)
        semantic_rows: list[NotesSearchCandidate] = []
        if self._embedding_service is not None:
            try:
                query_embedding = self._embedding_service.embed_texts([query]).embeddings[0].embedding
                semantic_rows = self._search_vector_candidates(query_embedding, limit, project)
            except Exception:
                semantic_rows = []
        merged: OrderedDict[str, NotesSearchCandidate] = OrderedDict()
        for candidate in [*lexical_rows, *semantic_rows]:
            current = merged.get(candidate.chunk_id)
            if current is None:
                merged[candidate.chunk_id] = candidate
                continue
            current.lexical_score = max(current.lexical_score, candidate.lexical_score)
            if candidate.vector_score is not None:
                current.vector_score = (
                    candidate.vector_score
                    if current.vector_score is None
                    else max(current.vector_score, candidate.vector_score)
                )
            if candidate.snippet and len(candidate.snippet) > len(current.snippet):
                current.snippet = candidate.snippet
            current.token_count = max(current.token_count, candidate.token_count)
        return list(merged.values())

    def _rerank_candidates(self, query: str, candidates: list[NotesSearchCandidate]) -> list[NotesSearchCandidate]:
        if not candidates:
            return []
        if self._rerank_service is None:
            return candidates
        try:
            rerank_scores = self._rerank_service.rerank(
                query,
                [self._candidate_text(candidate) for candidate in candidates],
            )
        except Exception:
            return candidates
        for candidate, rerank_score in zip(candidates, rerank_scores, strict=True):
            candidate.rerank_score = rerank_score
        return candidates

    def _deduplicate_by_note(self, candidates: list[NotesSearchCandidate]) -> list[NotesSearchCandidate]:
        best_by_note_id: OrderedDict[str, NotesSearchCandidate] = OrderedDict()
        for candidate in sorted(
            candidates,
            key=lambda item: combine_search_scores(
                lexical_score=item.lexical_score,
                vector_score=item.vector_score,
                rerank_score=item.rerank_score,
            ),
            reverse=True,
        ):
            note_id = candidate.note.id
            if note_id not in best_by_note_id:
                best_by_note_id[note_id] = candidate
        return list(best_by_note_id.values())

    def _trim_to_budget(self, candidates: list[NotesSearchCandidate], budget_tokens: int) -> list[NotesSearchCandidate]:
        if budget_tokens <= 0:
            return []
        trimmed: list[NotesSearchCandidate] = []
        total_tokens = 0
        for candidate in candidates:
            candidate_cost = self._estimate_candidate_tokens(candidate)
            if trimmed and total_tokens + candidate_cost > budget_tokens:
                break
            trimmed.append(candidate)
            total_tokens += candidate_cost
        return trimmed

    def _estimate_candidate_tokens(self, candidate: NotesSearchCandidate) -> int:
        return max(1, candidate.token_count + count_tokens(candidate.note.title) + count_tokens(candidate.snippet))

    @staticmethod
    def _candidate_text(candidate: NotesSearchCandidate) -> str:
        return f"{candidate.note.title}\n{candidate.snippet}".strip()

    def _search_lexical_candidates(self, query: str, limit: int, project: str) -> list[NotesSearchCandidate]:
        if hasattr(self._repository, "search_lexical_candidates"):
            return self._repository.search_lexical_candidates(query=query, limit=limit, project=project)
        results = self._repository.search(query=query, limit=limit, project=project)
        return [
            NotesSearchCandidate(
                note=result.note,
                chunk_id=result.chunk_id,
                snippet=result.snippet,
                token_count=count_tokens(result.snippet),
                lexical_score=result.score,
            )
            for result in results
        ]

    def _search_vector_candidates(
        self,
        query_embedding: list[float],
        limit: int,
        project: str,
    ) -> list[NotesSearchCandidate]:
        if not hasattr(self._repository, "search_vector_candidates"):
            return []
        return self._repository.search_vector_candidates(query_embedding=query_embedding, limit=limit, project=project)
