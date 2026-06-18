from __future__ import annotations

import json
from collections import OrderedDict
from time import monotonic

from anchor.adapters.sqlite_history_repository import SqliteHistoryRepository
from anchor.adapters.sqlite_ids import ensure_uuid7_str, uuid7_str
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.history.models import (
    HistoryListItem,
    HistoryRecord,
    HistorySearchCandidate,
    HistorySearchHit,
    HistorySearchResult,
)
from anchor.application.retrieval.compact_items import compact_history_item
from anchor.application.retrieval.document_chunking import DocumentChunkingService, count_tokens
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_scoring import combine_search_scores
from anchor.application.system.metadata_service import MetadataSchemaService


class HistoryService:
    def __init__(
        self,
        repository: SqliteHistoryRepository,
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

    def append(
        self,
        *,
        entry_type: str,
        payload: str,
        actor: str = "agent",
        correlation_id: str | None = None,
        project: str | None = None,
        metatags: dict[str, object] | None = None,
    ) -> HistoryRecord:
        self._require_non_empty(entry_type, "entry_type")
        self._require_non_empty(payload, "payload")
        resolved_project = project or self._project
        resolved_correlation_id = self._resolve_correlation_id(correlation_id)
        self._validate_metatags("history", metatags or {})
        chunks = self._chunking_service.chunk_note(title=entry_type, body=payload)
        result = self._repository.append(
            entry_type=entry_type,
            payload=payload,
            actor=actor,
            correlation_id=resolved_correlation_id,
            project=resolved_project,
            metatags=metatags or {},
            chunks=chunks,
        )
        self._queue_embeddings(result.id)
        self._drain_pending_embeddings(resolved_project, limit=1, time_budget_seconds=0.1)
        return result

    def update(
        self,
        history_id: str,
        *,
        entry_type: str | None = None,
        payload: str | None = None,
        actor: str | None = None,
        correlation_id: str | None = None,
        project: str | None = None,
        metatags: dict[str, object] | None = None,
    ) -> HistoryRecord:
        self._require_non_empty(history_id, "id")
        if entry_type is not None:
            self._require_non_empty(entry_type, "entry_type")
        if payload is not None:
            self._require_non_empty(payload, "payload")
        if correlation_id is not None:
            ensure_uuid7_str(correlation_id, "correlation_id")
        if all(value is None for value in (entry_type, payload, actor, correlation_id, metatags)):
            raise ValueError("update requires at least one field")
        resolved_project = project or self._project
        if metatags is not None:
            self._validate_metatags("history", metatags)
        chunks = None
        if entry_type is not None or payload is not None:
            current = self.get(history_id, project=resolved_project)
            updated_entry_type = entry_type if entry_type is not None else current.entry_type
            updated_payload = payload if payload is not None else current.payload
            chunks = self._chunking_service.chunk_note(title=updated_entry_type, body=updated_payload)
        result = self._repository.update(
            history_id,
            project=resolved_project,
            entry_type=entry_type,
            payload=payload,
            actor=actor,
            correlation_id=correlation_id,
            metatags=metatags,
            chunks=chunks,
        )
        if result is None:
            raise LookupError(f"history entry not found: {history_id}")
        if chunks is not None:
            self._queue_embeddings(result.id)
            self._drain_pending_embeddings(resolved_project, limit=1, time_budget_seconds=0.1)
        return result

    def delete(self, history_id: str, *, project: str | None = None) -> HistoryRecord:
        self._require_non_empty(history_id, "id")
        deleted = self._repository.delete(history_id, project=project or self._project)
        if deleted is None:
            raise LookupError(f"history entry not found: {history_id}")
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
    ) -> HistorySearchResult:
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
        deduplicated = self._deduplicate_by_history(reranked_candidates)
        trimmed = self._trim_to_budget(
            deduplicated,
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        results = [
            HistorySearchHit(
                history=self.get(candidate.history.id, project=resolved_project)
                if view == "full"
                else candidate.history,
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
        return HistorySearchResult(query=query, count=len(results), results=results)

    @staticmethod
    def _resolve_correlation_id(correlation_id: str | None) -> str:
        if correlation_id is None or not correlation_id.strip():
            return uuid7_str()
        HistoryService._validate_correlation_id(correlation_id)
        return correlation_id

    @staticmethod
    def _validate_correlation_id(correlation_id: str) -> None:
        ensure_uuid7_str(correlation_id, "correlation_id")

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

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

    def _collect_candidates(
        self,
        query: str,
        limit: int,
        project: str,
        *,
        prefer_lexical_only: bool = False,
        query_embedding: list[float] | None = None,
    ) -> list[HistorySearchCandidate]:
        lexical_rows = self._search_lexical_candidates(query, limit, project)
        semantic_rows: list[HistorySearchCandidate] = []
        resolved_query_embedding = query_embedding
        if resolved_query_embedding is None and self._embedding_service is not None and not prefer_lexical_only:
            try:
                resolved_query_embedding = self._embedding_service.embed_texts([query]).embeddings[0].embedding
            except Exception:
                resolved_query_embedding = None
        if resolved_query_embedding is not None and not prefer_lexical_only:
            semantic_rows = self._search_vector_candidates(resolved_query_embedding, limit, project)
        merged: OrderedDict[str, HistorySearchCandidate] = OrderedDict()
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

    def _rerank_candidates(self, query: str, candidates: list[HistorySearchCandidate]) -> list[HistorySearchCandidate]:
        if not candidates:
            return []
        if self._rerank_service is None:
            return candidates
        rerank_scores = self._rerank_service.rerank(query, [candidate.snippet for candidate in candidates])
        for candidate, rerank_score in zip(candidates, rerank_scores, strict=True):
            candidate.rerank_score = rerank_score
        return candidates

    def _deduplicate_by_history(self, candidates: list[HistorySearchCandidate]) -> list[HistorySearchCandidate]:
        best_by_history: OrderedDict[str, HistorySearchCandidate] = OrderedDict()
        for candidate in candidates:
            key = candidate.history.id
            current = best_by_history.get(key)
            score = combine_search_scores(
                lexical_score=candidate.lexical_score,
                vector_score=candidate.vector_score,
                rerank_score=candidate.rerank_score,
            )
            if current is None:
                best_by_history[key] = candidate
                continue
            current_score = combine_search_scores(
                lexical_score=current.lexical_score,
                vector_score=current.vector_score,
                rerank_score=current.rerank_score,
            )
            if score > current_score:
                best_by_history[key] = candidate
        return list(best_by_history.values())

    def _search_lexical_candidates(self, query: str, limit: int, project: str) -> list[HistorySearchCandidate]:
        if hasattr(self._repository, "search_lexical_candidates"):
            return self._repository.search_lexical_candidates(query=query, limit=limit, project=project)
        results = self._repository.search(query=query, limit=limit, project=project)
        return [
            HistorySearchCandidate(
                history=self._as_search_item(result.history),
                chunk_id=result.chunk_id,
                snippet=result.snippet,
                token_count=max(1, count_tokens(result.snippet)),
                lexical_score=result.score,
            )
            for result in results
        ]

    def _search_vector_candidates(
        self,
        query_embedding: list[float],
        limit: int,
        project: str,
    ) -> list[HistorySearchCandidate]:
        if not hasattr(self._repository, "search_vector_candidates"):
            return []
        return self._repository.search_vector_candidates(query_embedding=query_embedding, limit=limit, project=project)

    def _trim_to_budget(
        self, results: list[HistorySearchCandidate], budget_tokens: int
    ) -> list[HistorySearchCandidate]:
        if budget_tokens <= 0:
            return []
        trimmed: list[HistorySearchCandidate] = []
        total_tokens = 0
        for result in results:
            result_cost = self._estimate_result_tokens(result)
            if trimmed and total_tokens + result_cost > budget_tokens:
                break
            trimmed.append(result)
            total_tokens += result_cost
        return trimmed

    @staticmethod
    def _estimate_result_tokens(result: HistorySearchCandidate) -> int:
        return max(
            1,
            count_tokens(result.history.entry_type) + count_tokens(result.history.actor) + count_tokens(result.snippet),
        )

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _as_search_item(history: HistoryRecord | HistoryListItem) -> HistoryListItem:
        return compact_history_item(history)

    def get(self, history_id: str, *, project: str | None = None) -> HistoryRecord:
        self._require_non_empty(history_id, "id")
        history = self._repository.get(history_id, project=project or self._project)
        if history is None:
            raise LookupError(f"history entry not found: {history_id}")
        return history
