from __future__ import annotations

import unittest
import uuid

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.application.embeddings.models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.history.models import HistoryListItem, HistoryRecord, HistorySearchCandidate
from anchor.application.history.service import HistoryService
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_service import RerankService

HISTORY_ID = uuid7_str()
HISTORY_CHUNK_ID = uuid7_str()


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.created: HistoryRecord | None = None
        self._chunks: list[DocumentChunkRecord] = []
        self.stored_embeddings: list[ChunkEmbeddingRecord] = []
        self.pending_embedding_ids: list[str] = []
        self.deleted: HistoryRecord | None = None

    def append(
        self,
        *,
        entry_type: str,
        payload: str,
        actor: str = "agent",
        correlation_id: str = "",
        project: str,
        metatags: dict[str, object] | None = None,
        chunks,
    ) -> HistoryRecord:
        self.created = HistoryRecord(
            id=HISTORY_ID,
            project=project,
            metatags=metatags or {},
            entry_type=entry_type,
            actor=actor,
            payload=payload,
            correlation_id=correlation_id,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )
        self._chunks = [
            DocumentChunkRecord(
                id=HISTORY_CHUNK_ID,
                document_id=HISTORY_ID,
                project=project,
                metatags=metatags or {},
                chunk_index=0,
                chunk_text=chunks[0].chunk_text,
                token_count=chunks[0].token_count,
                created_at="2026-06-13T00:00:00+00:00",
            )
        ]
        return self.created

    def get(self, history_id: str, *, project: str):  # pragma: no cover - not used in test
        del project
        return self.created if self.created and self.created.id == history_id else None

    def update(
        self,
        history_id: str,
        *,
        project: str,
        entry_type: str | None = None,
        payload: str | None = None,
        actor: str | None = None,
        correlation_id: str | None = None,
        metatags: dict[str, object] | None = None,
        chunks=None,
    ) -> HistoryRecord | None:
        if self.created is None or self.created.id != history_id:
            return None
        updated = self.created.model_copy(
            update={
                "project": project,
                "entry_type": entry_type if entry_type is not None else self.created.entry_type,
                "payload": payload if payload is not None else self.created.payload,
                "actor": actor if actor is not None else self.created.actor,
                "correlation_id": correlation_id if correlation_id is not None else self.created.correlation_id,
                "metatags": metatags if metatags is not None else self.created.metatags,
            }
        )
        self.created = updated
        if chunks is not None:
            self._chunks = [
                DocumentChunkRecord(
                    id=HISTORY_CHUNK_ID,
                    document_id=history_id,
                    project=project,
                    metatags=updated.metatags,
                    chunk_index=0,
                    chunk_text=chunks[0].chunk_text,
                    token_count=chunks[0].token_count,
                    created_at="2026-06-13T00:00:00+00:00",
                )
            ]
        return self.created

    def delete(self, history_id: str, *, project: str) -> HistoryRecord | None:
        del project
        if self.created is None or self.created.id != history_id:
            return None
        self.deleted = self.created
        self.created = None
        self._chunks = []
        return self.deleted

    def list_chunks(self, document_id: str):
        return self._chunks if document_id == HISTORY_ID else []

    def store_chunk_embeddings(self, embeddings, *, project: str, metatags: str, created_at: str):
        del project, metatags, created_at
        self.stored_embeddings.extend(embeddings)

    def enqueue_embedding_index(self, document_id: str):
        if document_id not in self.pending_embedding_ids:
            self.pending_embedding_ids.append(document_id)

    def pending_embedding_documents(self, *, project: str, limit: int = 8):
        del project
        return self.pending_embedding_ids[:limit]

    def mark_embedding_index_ready(self, document_id: str):
        if document_id in self.pending_embedding_ids:
            self.pending_embedding_ids.remove(document_id)

    def mark_embedding_index_error(self, document_id: str, *, last_error: str):
        del last_error
        if document_id in self.pending_embedding_ids:
            self.pending_embedding_ids.remove(document_id)

    def search_lexical_candidates(self, query: str, limit: int, *, project: str):
        del query, project
        if self.created is None:
            return []
        return [
            HistorySearchCandidate(
                history=HistoryListItem(
                    id=self.created.id,
                    project=self.created.project,
                    entry_type=self.created.entry_type,
                    actor=self.created.actor,
                    correlation_id=self.created.correlation_id,
                    created_at=self.created.created_at,
                ),
                chunk_id=HISTORY_CHUNK_ID,
                snippet="history search snippet with useful words",
                token_count=6,
                lexical_score=0.75,
            )
        ][:limit]

    def search_vector_candidates(self, query_embedding: list[float], limit: int, *, project: str):
        del query_embedding, project
        if self.created is None:
            return []
        return [
            HistorySearchCandidate(
                history=HistoryListItem(
                    id=self.created.id,
                    project=self.created.project,
                    entry_type=self.created.entry_type,
                    actor=self.created.actor,
                    correlation_id=self.created.correlation_id,
                    created_at=self.created.created_at,
                ),
                chunk_id=HISTORY_CHUNK_ID,
                snippet="history vector snippet with more detail",
                token_count=7,
                vector_score=0.9,
            )
        ][:limit]


class FakeEmbeddingsProvider:
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        del model
        return [[float(len(text))] for text in texts]


class HistoryServiceTest(unittest.TestCase):
    def test_append_queues_embeddings(self) -> None:
        repo = FakeHistoryRepository()
        service = HistoryService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        history = service.append(entry_type="deploy", payload="one two three", project="repo-a")

        self.assertEqual(history.id, HISTORY_ID)
        self.assertEqual(uuid.UUID(history.correlation_id).version, 7)
        self.assertEqual(repo.pending_embedding_ids, [HISTORY_ID])
        self.assertEqual(len(repo.stored_embeddings), 0)

    def test_search_drains_pending_embeddings_and_returns_hits(self) -> None:
        repo = FakeHistoryRepository()
        service = HistoryService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
            rerank_service=RerankService(embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-rerank")),
            budget_tokens=100,
        )

        service.append(entry_type="deploy", payload="one two three", project="repo-a")
        result = service.search("deploy", project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].history.id, HISTORY_ID)
        self.assertEqual(repo.pending_embedding_ids, [])
        self.assertGreater(len(repo.stored_embeddings), 0)
        self.assertEqual(result.results[0].history.project, "repo-a")

    def test_update_requeues_embeddings_and_changes_fields(self) -> None:
        repo = FakeHistoryRepository()
        service = HistoryService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        service.append(entry_type="deploy", payload="one two three", project="repo-a")
        updated = service.update(HISTORY_ID, payload="four five six", actor="bot", project="repo-a")

        self.assertEqual(updated.payload, "four five six")
        self.assertEqual(updated.actor, "bot")
        self.assertEqual(repo.pending_embedding_ids, [HISTORY_ID])

    def test_append_rejects_non_uuidv7_correlation_id(self) -> None:
        repo = FakeHistoryRepository()
        service = HistoryService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
        )

        with self.assertRaises(ValueError):
            service.append(entry_type="deploy", payload="one two three", correlation_id="not-a-uuid", project="repo-a")

    def test_delete_removes_history_entry(self) -> None:
        repo = FakeHistoryRepository()
        service = HistoryService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
        )

        service.append(entry_type="deploy", payload="one two three", project="repo-a")
        deleted = service.delete(HISTORY_ID, project="repo-a")

        self.assertEqual(deleted.id, HISTORY_ID)
        self.assertIsNone(repo.created)
        with self.assertRaises(LookupError):
            service.get(HISTORY_ID, project="repo-a")
