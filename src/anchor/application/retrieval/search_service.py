from __future__ import annotations

import base64
import json
from collections import OrderedDict

from anchor.application.embeddings.service import EmbeddingService
from anchor.application.files.models import FilesSearchResult
from anchor.application.files.service import FilesService
from anchor.application.history.models import HistorySearchResult
from anchor.application.history.service import HistoryService
from anchor.application.notes.models import NotesSearchResult
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.retrieval.search_models import SearchHit, SearchResult, SearchStats
from anchor.application.retrieval.search_query import MAX_RETRIEVAL_LIMIT, SearchQuery
from anchor.application.tasks.models import TasksSearchResult
from anchor.application.tasks.service import TasksService

_SUPPORTED_TYPES = {"notes", "tasks", "history", "files"}


class SearchService:
    def __init__(
        self,
        notes_service: NotesService,
        history_service: HistoryService,
        tasks_service: TasksService,
        files_service: FilesService,
        *,
        embedding_service: EmbeddingService | None = None,
        budget_tokens: int = 800,
    ) -> None:
        self._notes_service = notes_service
        self._history_service = history_service
        self._tasks_service = tasks_service
        self._files_service = files_service
        self._embedding_service = embedding_service
        self._budget_tokens = budget_tokens

    def search(self, search_query: SearchQuery) -> SearchResult:
        unsupported = [search_type for search_type in search_query.types if search_type not in _SUPPORTED_TYPES]
        if unsupported:
            raise ValueError(f"unsupported search types: {', '.join(unsupported)}")
        requested_types = search_query.types or ["notes", "tasks", "history", "files"]
        requested_projects = search_query.projects or [search_query.project]
        prefer_lexical_only = self._prefer_lexical_only(search_query.query)
        query_embedding = self._resolve_query_embedding(
            search_query.query,
            prefer_lexical_only,
            requested_projects,
        )
        per_type_budgets = self._allocate_budgets(search_query.budget_tokens, requested_types, search_query.weights)
        project_count = len(requested_projects)
        expanded_limit = min(
            MAX_RETRIEVAL_LIMIT,
            max(search_query.limit * 4, search_query.limit + 1),
        )
        per_project_candidate_limit = max(1, (expanded_limit + project_count - 1) // project_count)
        candidate_counts: dict[str, int] = {}
        candidates: list[SearchHit] = []
        for search_type in requested_types:
            for project in requested_projects:
                per_project_budget = max(1, per_type_budgets[search_type] // project_count)
                if search_type == "notes":
                    notes_result = self._notes_service.search(
                        search_query.query,
                        limit=per_project_candidate_limit,
                        project=project,
                        budget_tokens=per_project_budget,
                        prefer_lexical_only=prefer_lexical_only,
                        query_embedding=query_embedding,
                    )
                    candidate_counts[search_type] = candidate_counts.get(search_type, 0) + notes_result.count
                    candidates.extend(self._notes_hits(notes_result, project))
                elif search_type == "tasks":
                    tasks_result = self._tasks_service.search(
                        search_query.query,
                        limit=per_project_candidate_limit,
                        project=project,
                        budget_tokens=per_project_budget,
                        query_embedding=query_embedding,
                    )
                    candidate_counts[search_type] = candidate_counts.get(search_type, 0) + tasks_result.count
                    candidates.extend(self._tasks_hits(tasks_result, project))
                elif search_type == "history":
                    history_result = self._history_service.search(
                        search_query.query,
                        limit=per_project_candidate_limit,
                        project=project,
                        budget_tokens=per_project_budget,
                        prefer_lexical_only=prefer_lexical_only,
                        query_embedding=query_embedding,
                    )
                    candidate_counts[search_type] = candidate_counts.get(search_type, 0) + history_result.count
                    candidates.extend(self._history_hits(history_result, project))
                elif search_type == "files":
                    files_result = self._files_service.search(
                        search_query.query,
                        limit=per_project_candidate_limit,
                        project=project,
                        budget_tokens=per_project_budget,
                        prefer_lexical_only=prefer_lexical_only,
                        query_embedding=query_embedding,
                    )
                    candidate_counts[search_type] = candidate_counts.get(search_type, 0) + files_result.count
                    candidates.extend(self._files_hits(files_result, project))
        deduplicated = self._deduplicate(candidates)
        ordered = sorted(
            deduplicated,
            key=lambda item: (-item.score, item.entity_type, item.entity_id),
        )
        filtered = self._apply_cursor(ordered, search_query.cursor)
        trimmed = self._trim_to_budget(filtered, search_query.budget_tokens)
        page = trimmed[: search_query.limit]
        next_cursor = self._encode_cursor(page[-1]) if len(filtered) > len(page) and page else None
        stats = SearchStats(
            budget_tokens=search_query.budget_tokens,
            consumed_tokens=self._estimate_consumed_tokens(page),
            candidate_counts=candidate_counts,
            deduplicated_count=len(deduplicated),
            returned_count=len(page),
        )
        return SearchResult(
            query=search_query,
            count=len(page),
            results=page,
            next_cursor=next_cursor,
            stats=stats if search_query.explain else None,
        )

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

    def _history_hits(self, result: HistorySearchResult, project: str) -> list[SearchHit]:
        return [
            SearchHit(
                entity_type="history",
                entity_id=hit.history.id,
                project=hit.history.project,
                title=f"{hit.history.entry_type} · {hit.history.actor}",
                score=hit.score,
                snippet=hit.snippet,
                attributes={
                    "entry_type": hit.history.entry_type,
                    "actor": hit.history.actor,
                    "correlation_id": hit.history.correlation_id,
                },
            )
            for hit in result.results
        ]

    def _files_hits(self, result: FilesSearchResult, project: str) -> list[SearchHit]:
        return [
            SearchHit(
                entity_type="files",
                entity_id=hit.file.id,
                project=project,
                title=hit.file.path,
                score=hit.score,
                snippet=hit.snippet,
                attributes={
                    "path": hit.file.path,
                    "root_path": hit.file.root_path,
                    "language": hit.file.language,
                    "file_size": hit.file.file_size,
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
        return max(
            1,
            count_tokens(hit.title)
            + count_tokens(hit.snippet)
            + count_tokens(json.dumps(hit.attributes, ensure_ascii=False, separators=(",", ":"))),
        )

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

    @staticmethod
    def _prefer_lexical_only(query: str) -> bool:
        return count_tokens(query) <= 1 or len(query.strip()) <= 4

    def _resolve_query_embedding(
        self,
        query: str,
        prefer_lexical_only: bool,
        projects: list[str],
    ) -> list[float] | None:
        if prefer_lexical_only or self._embedding_service is None:
            return None
        try:
            return self._embedding_service.embed_texts(
                [query], projects=projects
            ).embeddings[0].embedding
        except Exception:
            return None

    @staticmethod
    def _encode_cursor(hit: SearchHit) -> str:
        payload = json.dumps(
            {
                "score": hit.score,
                "entity_type": hit.entity_type,
                "entity_id": hit.entity_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[float, str, str] | None:
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
        score = payload.get("score")
        entity_type = payload.get("entity_type")
        entity_id = payload.get("entity_id")
        if not isinstance(score, (int, float)) or not isinstance(entity_type, str) or not isinstance(entity_id, str):
            raise ValueError("cursor must be an opaque pagination token")
        return float(score), entity_type, entity_id

    def _apply_cursor(self, hits: list[SearchHit], cursor: str | None) -> list[SearchHit]:
        decoded = self._decode_cursor(cursor)
        if decoded is None:
            return hits
        cursor_score, cursor_type, cursor_id = decoded
        filtered: list[SearchHit] = []
        for hit in hits:
            current_key = (-hit.score, hit.entity_type, hit.entity_id)
            cursor_key = (-cursor_score, cursor_type, cursor_id)
            if current_key > cursor_key:
                filtered.append(hit)
        return filtered
