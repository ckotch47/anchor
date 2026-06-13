from __future__ import annotations

import json
from collections import OrderedDict

from anchor.application.notes.models import NotesSearchResult
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.retrieval.search_models import SearchHit, SearchResult, SearchStats
from anchor.application.retrieval.search_query import SearchQuery
from anchor.application.tasks.models import TasksSearchResult
from anchor.application.tasks.service import TasksService

_SUPPORTED_TYPES = {"notes", "tasks"}


class SearchService:
    def __init__(
        self,
        notes_service: NotesService,
        tasks_service: TasksService,
        *,
        budget_tokens: int = 800,
    ) -> None:
        self._notes_service = notes_service
        self._tasks_service = tasks_service
        self._budget_tokens = budget_tokens

    def search(self, search_query: SearchQuery) -> SearchResult:
        unsupported = [search_type for search_type in search_query.types if search_type not in _SUPPORTED_TYPES]
        if unsupported:
            raise ValueError(f"unsupported search types: {', '.join(unsupported)}")
        requested_types = search_query.types or ["notes", "tasks"]
        per_type_budgets = self._allocate_budgets(search_query.budget_tokens, requested_types, search_query.weights)
        candidate_counts: dict[str, int] = {}
        candidates: list[SearchHit] = []
        candidate_limit = max(search_query.limit * 4, search_query.limit)
        for search_type in requested_types:
            if search_type == "notes":
                notes_result = self._notes_service.search(
                    search_query.query,
                    limit=candidate_limit,
                    project=search_query.project,
                    budget_tokens=per_type_budgets[search_type],
                )
                candidate_counts[search_type] = notes_result.count
                candidates.extend(self._notes_hits(notes_result, search_query.project))
            elif search_type == "tasks":
                tasks_result = self._tasks_service.search(
                    search_query.query,
                    limit=candidate_limit,
                    project=search_query.project,
                    budget_tokens=per_type_budgets[search_type],
                )
                candidate_counts[search_type] = tasks_result.count
                candidates.extend(self._tasks_hits(tasks_result, search_query.project))
        deduplicated = self._deduplicate(candidates)
        ordered = sorted(deduplicated, key=lambda item: item.score, reverse=True)
        trimmed = self._trim_to_budget(ordered, search_query.budget_tokens)
        stats = SearchStats(
            budget_tokens=search_query.budget_tokens,
            consumed_tokens=self._estimate_consumed_tokens(trimmed),
            candidate_counts=candidate_counts,
            deduplicated_count=len(deduplicated),
            returned_count=len(trimmed),
        )
        return SearchResult(query=search_query, count=len(trimmed), results=trimmed, stats=stats if search_query.explain else None)

    def _notes_hits(self, result: NotesSearchResult, project: str) -> list[SearchHit]:
        return [
            SearchHit(
                entity_type="notes",
                entity_id=hit.note.id,
                project=project,
                title=hit.note.title,
                score=hit.score,
                snippet=hit.snippet,
                attributes={"pinned": hit.note.pinned},
            )
            for hit in result.results
        ]

    def _tasks_hits(self, result: TasksSearchResult, project: str) -> list[SearchHit]:
        return [
            SearchHit(
                entity_type="tasks",
                entity_id=hit.task.id,
                project=project,
                title=hit.task.title,
                score=hit.score,
                snippet=hit.snippet,
                attributes={
                    "status": hit.task.status,
                    "priority": hit.task.priority,
                },
            )
            for hit in result.results
        ]

    def _deduplicate(self, hits: list[SearchHit]) -> list[SearchHit]:
        best_by_key: OrderedDict[str, SearchHit] = OrderedDict()
        for hit in hits:
            key = f"{hit.entity_type}:{hit.entity_id}:{hit.project}"
            current = best_by_key.get(key)
            if current is None or hit.score > current.score:
                best_by_key[key] = hit
        return list(best_by_key.values())

    def _trim_to_budget(self, hits: list[SearchHit], budget_tokens: int) -> list[SearchHit]:
        if budget_tokens <= 0:
            return []
        trimmed: list[SearchHit] = []
        consumed = 0
        for hit in hits:
            hit_cost = self._estimate_hit_tokens(hit)
            if trimmed and consumed + hit_cost > budget_tokens:
                break
            trimmed.append(hit)
            consumed += hit_cost
        return trimmed

    def _estimate_hit_tokens(self, hit: SearchHit) -> int:
        return max(1, count_tokens(hit.title) + count_tokens(hit.snippet) + count_tokens(json.dumps(hit.attributes, ensure_ascii=False, separators=(",", ":"))))

    def _estimate_consumed_tokens(self, hits: list[SearchHit]) -> int:
        return sum(self._estimate_hit_tokens(hit) for hit in hits)

    def _allocate_budgets(
        self,
        budget_tokens: int,
        search_types: list[str],
        weights: dict[str, float],
    ) -> dict[str, int]:
        if not search_types:
            return {}
        if budget_tokens <= 0:
            return {search_type: 0 for search_type in search_types}
        resolved_weights = [weights.get(search_type, 1.0) for search_type in search_types]
        total_weight = sum(resolved_weights)
        if total_weight <= 0:
            total_weight = float(len(search_types))
            resolved_weights = [1.0 for _ in search_types]
        allocations: dict[str, int] = {}
        remaining = budget_tokens
        for index, search_type in enumerate(search_types):
            if index == len(search_types) - 1:
                allocations[search_type] = remaining
                break
            share = max(1, int(budget_tokens * resolved_weights[index] / total_weight))
            remaining -= share
            allocations[search_type] = share
        return allocations
