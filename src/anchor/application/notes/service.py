from __future__ import annotations

import base64
import json
from collections import OrderedDict
from time import monotonic

from anchor.adapters.sqlite_ids import ensure_uuid7_str, uuid7_str
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.models import (
    NoteRecord,
    NotesListResult,
    NotesSearchCandidate,
    NotesSearchHit,
    NotesSearchResult,
)
from anchor.application.retrieval.compact_items import compact_note_list_item, compact_note_search_item
from anchor.application.retrieval.document_chunking import DocumentChunkingService, count_tokens
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_scoring import combine_search_scores
from anchor.application.system.metadata_service import MetadataSchemaService


class NotesService:
    def __init__(
        self,
        repository: SqliteNotesRepository,
        chunking_service: DocumentChunkingService,
        project: str,
        embedding_service: EmbeddingService | None = None,
        rerank_service: RerankService | None = None,
        metadata_service: MetadataSchemaService | None = None,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._chunking_service = chunking_service
        self._project = project
        self._embedding_service = embedding_service
        self._rerank_service = rerank_service
        self._metadata_service = metadata_service
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
        resolved_correlation_id = uuid7_str()
        self._validate_metatags("notes", metatags or {})
        chunks = self._chunking_service.chunk_note(title=title, body=body)
        result = self._repository.create(
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            pinned=pinned,
            project=resolved_project,
            correlation_id=resolved_correlation_id,
            metatags=metatags or {},
            chunks=chunks,
        )
        self._queue_embeddings(result.id)
        self._drain_pending_embeddings(resolved_project, limit=1, time_budget_seconds=0.1)
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
        correlation_id: str | None = None,
        metatags: dict[str, object] | None = None,
    ) -> NoteRecord:
        self._require_non_empty(note_id, "id")
        if title is not None:
            self._require_non_empty(title, "title")
        if body is not None:
            self._require_non_empty(body, "body")
        if all(value is None for value in (title, body, source, source_ref, pinned, correlation_id, metatags)):
            raise ValueError("update requires at least one field")
        resolved_project = project or self._project
        if correlation_id is not None:
            self._validate_correlation_id(correlation_id)
        if metatags is not None:
            self._validate_metatags("notes", metatags)
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
            correlation_id=correlation_id,
            metatags=metatags,
            chunks=chunks,
        )
        if result is None:
            raise LookupError(f"note not found: {note_id}")
        if chunks is not None:
            self._queue_embeddings(result.id)
            self._drain_pending_embeddings(resolved_project, limit=1, time_budget_seconds=0.1)
        return result

    def list(
        self,
        limit: int = 20,
        *,
        project: str | None = None,
        cursor: str | None = None,
        view: str = "compact",
    ) -> NotesListResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        cursor_id = self._decode_cursor(cursor)
        notes = self._repository.list(
            limit + 1,
            project=project or self._project,
            cursor_id=cursor_id,
        )
        next_cursor = None
        if len(notes) > limit:
            next_cursor = self._encode_cursor(notes[limit - 1].id)
            notes = notes[:limit]
        return NotesListResult(
            count=len(notes),
            notes=notes if view == "full" else [compact_note_list_item(note) for note in notes],
            next_cursor=next_cursor,
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
        view: str = "compact",
        prefer_lexical_only: bool = False,
        query_embedding: list[float] | None = None,
    ) -> NotesSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        resolved_project = project or self._project
        if not prefer_lexical_only:
            self._drain_pending_embeddings(resolved_project)
        candidate_limit = max(limit * 4, limit)
        candidates = self._collect_candidates(
            query,
            candidate_limit,
            resolved_project,
            prefer_lexical_only=prefer_lexical_only,
            query_embedding=query_embedding,
        )
        reranked_candidates = self._rerank_candidates(query, candidates) if not prefer_lexical_only else candidates
        deduplicated = self._deduplicate_by_note(reranked_candidates)
        trimmed = self._trim_to_budget(
            deduplicated,
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        results = [
            NotesSearchHit(
                note=self.get(candidate.note.id, project=resolved_project)
                if view == "full"
                else candidate.note,
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

    @staticmethod
    def _validate_correlation_id(correlation_id: str) -> None:
        ensure_uuid7_str(correlation_id, "correlation_id")

    def _validate_metatags(self, entity_type: str, metatags: dict[str, object]) -> None:
        if self._metadata_service is None:
            return
        self._metadata_service.validate(entity_type, metatags)

    def _queue_embeddings(self, document_id: str) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "enqueue_embedding_index"):
            return
        try:
            self._repository.enqueue_embedding_index(document_id)
        except Exception:
            return

    def _drain_pending_embeddings(
        self,
        project: str,
        *,
        limit: int = 8,
        time_budget_seconds: float | None = None,
    ) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "pending_embedding_documents"):
            return
        try:
            pending_documents = self._repository.pending_embedding_documents(project=project, limit=limit)
        except Exception:
            return
        started_at = monotonic()
        for document_id in pending_documents:
            if time_budget_seconds is not None and monotonic() - started_at >= time_budget_seconds:
                break
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

    @staticmethod
    def _encode_cursor(note_id: str) -> str:
        payload = json.dumps({"id": note_id}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> str | None:
        if cursor is None or not cursor.strip():
            return None
        padding = "=" * (-len(cursor) % 4)
        try:
            raw_value = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii")).decode("utf-8")
            payload = json.loads(raw_value)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("cursor must be an opaque pagination token") from exc
        if not isinstance(payload, dict):
            raise ValueError("cursor must be an opaque pagination token")
        note_id = payload.get("id")
        if not isinstance(note_id, str) or not note_id:
            raise ValueError("cursor must be an opaque pagination token")
        return note_id

    def _collect_candidates(
        self,
        query: str,
        limit: int,
        project: str,
        *,
        prefer_lexical_only: bool = False,
        query_embedding: list[float] | None = None,
    ) -> list[NotesSearchCandidate]:
        lexical_rows = self._search_lexical_candidates(query, limit, project)
        semantic_rows: list[NotesSearchCandidate] = []
        resolved_query_embedding = query_embedding
        if resolved_query_embedding is None and self._embedding_service is not None and not prefer_lexical_only:
            try:
                resolved_query_embedding = self._embedding_service.embed_texts([query]).embeddings[0].embedding
            except Exception:
                resolved_query_embedding = None
        if resolved_query_embedding is not None and not prefer_lexical_only:
            semantic_rows = self._search_vector_candidates(resolved_query_embedding, limit, project)
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
                note=compact_note_search_item(result.note),
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
