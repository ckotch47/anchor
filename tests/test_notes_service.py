from __future__ import annotations

import unittest

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.application.embeddings.models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.models import NoteRecord, NoteSearchItem, NotesSearchCandidate
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_service import RerankService

NOTE_ID = uuid7_str()
NOTE_OTHER_ID = uuid7_str()
NOTE_CHUNK_ID = uuid7_str()
NOTE_LEX_CHUNK_ID = uuid7_str()
NOTE_VEC_CHUNK_ID = uuid7_str()


class FakeNotesRepository:
    def __init__(self) -> None:
        self.created: NoteRecord | None = None
        self._chunks = []
        self.stored_embeddings: list[ChunkEmbeddingRecord] = []
        self.pending_embedding_ids: list[str] = []

    def create(
        self,
        *,
        title: str,
        body: str,
        source: str,
        source_ref: str,
        pinned: bool,
        project: str,
        metatags: dict[str, object] | None = None,
        chunks,
    ):
        self.created = NoteRecord(
            id=NOTE_ID,
            project=project,
            metatags=metatags or {},
            title=title,
            body=body,
            source=source,
            source_ref=source_ref,
            note_kind="note",
            pinned=pinned,
            archived_at=None,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )
        self._chunks = [
            DocumentChunkRecord(
                id=NOTE_CHUNK_ID,
                document_id=NOTE_ID,
                project="workspace",
                metatags={},
                chunk_index=0,
                chunk_text=chunks[0].chunk_text,
                token_count=chunks[0].token_count,
                created_at="2026-06-13T00:00:00+00:00",
            )
        ]
        return self.created

    def update(
        self,
        note_id: str,
        *,
        project: str,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        pinned: bool | None = None,
        metatags: dict[str, object] | None = None,
        chunks=None,
    ) -> NoteRecord | None:
        if self.created is None or self.created.id != note_id:
            return None
        updated = self.created.model_copy(
            update={
                "project": project,
                "title": title if title is not None else self.created.title,
                "body": body if body is not None else self.created.body,
                "source": source if source is not None else self.created.source,
                "source_ref": source_ref if source_ref is not None else self.created.source_ref,
                "pinned": pinned if pinned is not None else self.created.pinned,
                "metatags": metatags if metatags is not None else self.created.metatags,
            }
        )
        self.created = updated
        if chunks is not None:
            self._chunks = [
                DocumentChunkRecord(
                    id=NOTE_CHUNK_ID,
                    document_id=note_id,
                    project=project,
                    metatags=updated.metatags,
                    chunk_index=0,
                    chunk_text=chunks[0].chunk_text,
                    token_count=chunks[0].token_count,
                    created_at="2026-06-13T00:00:00+00:00",
                )
            ]
        return self.created

    def list(self, limit: int, *, project: str):  # pragma: no cover - not used in test
        return []

    def get(self, note_id: str, *, project: str):  # pragma: no cover - not used in test
        return self.created if self.created and self.created.id == note_id else None

    def list_chunks(self, document_id: str):
        return self._chunks if document_id == NOTE_ID else []

    def store_chunk_embeddings(self, embeddings, *, project: str, metatags: str, created_at: str):
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

    def search(self, query: str, limit: int, *, project: str):  # pragma: no cover - not used in test
        return []

    def delete(self, note_id: str, *, project: str):
        del project
        if self.created is None or self.created.id != note_id:
            return None
        deleted = self.created
        self.created = None
        self._chunks = []
        return deleted


class FakeEmbeddingsProvider:
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FailingEmbeddingsProvider:
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("embeddings unavailable")


class SearchPipelineRepository(FakeNotesRepository):
    def __init__(self) -> None:
        super().__init__()
        self.note_one = NoteRecord(
            id=NOTE_ID,
            project="repo-a",
            metatags={},
            title="Alpha note",
            body="alpha body content",
            source="cli",
            source_ref="",
            note_kind="note",
            pinned=False,
            archived_at=None,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )
        self.note_two = NoteRecord(
            id=NOTE_OTHER_ID,
            project="repo-a",
            metatags={},
            title="Beta note",
            body="beta body content",
            source="cli",
            source_ref="",
            note_kind="note",
            pinned=False,
            archived_at=None,
            created_at="2026-06-13T00:00:00+00:00",
            updated_at="2026-06-13T00:00:00+00:00",
        )

    def search_lexical_candidates(self, query: str, limit: int, *, project: str):
        del query, project
        return [
            NotesSearchCandidate(
                note=NoteSearchItem(
                    id=self.note_one.id,
                    project=self.note_one.project,
                    title=self.note_one.title,
                    pinned=self.note_one.pinned,
                    created_at=self.note_one.created_at,
                ),
                chunk_id=NOTE_LEX_CHUNK_ID,
                snippet="alpha lexical snippet with many words to consume budget",
                token_count=8,
                lexical_score=0.95,
            ),
            NotesSearchCandidate(
                note=NoteSearchItem(
                    id=self.note_two.id,
                    project=self.note_two.project,
                    title=self.note_two.title,
                    pinned=self.note_two.pinned,
                    created_at=self.note_two.created_at,
                ),
                chunk_id=uuid7_str(),
                snippet="beta lexical snippet that will be trimmed later",
                token_count=8,
                lexical_score=0.85,
            ),
        ][:limit]

    def search_vector_candidates(self, query_embedding: list[float], limit: int, *, project: str):
        del query_embedding, project
        return [
            NotesSearchCandidate(
                note=NoteSearchItem(
                    id=self.note_one.id,
                    project=self.note_one.project,
                    title=self.note_one.title,
                    pinned=self.note_one.pinned,
                    created_at=self.note_one.created_at,
                ),
                chunk_id=NOTE_VEC_CHUNK_ID,
                snippet="alpha vector snippet with many words to consume budget",
                token_count=8,
                vector_score=0.99,
            ),
            NotesSearchCandidate(
                note=NoteSearchItem(
                    id=self.note_two.id,
                    project=self.note_two.project,
                    title=self.note_two.title,
                    pinned=self.note_two.pinned,
                    created_at=self.note_two.created_at,
                ),
                chunk_id=uuid7_str(),
                snippet="beta vector snippet that will be trimmed later",
                token_count=8,
                vector_score=0.80,
            ),
        ][:limit]


class NotesServiceTest(unittest.TestCase):
    def test_add_queues_embeddings(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        note = service.add(title="Hello", body="one two three", source="cli")

        self.assertEqual(note.id, NOTE_ID)
        self.assertEqual(repo.pending_embedding_ids, [NOTE_ID])
        self.assertEqual(len(repo.stored_embeddings), 0)

    def test_update_requeues_embeddings(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        service.add(title="Hello", body="one two three", source="cli")
        updated = service.update(NOTE_ID, title="Hello again", body="four five six")

        self.assertEqual(updated.title, "Hello again")
        self.assertEqual(updated.body, "four five six")
        self.assertEqual(repo.pending_embedding_ids, [NOTE_ID])
        self.assertEqual(len(repo.stored_embeddings), 0)

    def test_search_drains_pending_embeddings(self) -> None:
        repo = SearchPipelineRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="embed"),
            rerank_service=RerankService(
                embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="rerank")
            ),
            budget_tokens=100,
        )

        service.add(title="Hello", body="alpha body content", source="cli", project="repo-a")
        self.assertEqual(len(repo.stored_embeddings), 0)

        result = service.search("alpha", limit=4, project="repo-a")

        self.assertEqual(result.count, 2)
        self.assertGreaterEqual(len(repo.stored_embeddings), 1)

    def test_update_rejects_empty_payload(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
        )

        service.add(title="Hello", body="one two three", source="cli")

        with self.assertRaises(ValueError):
            service.update(NOTE_ID)

    def test_search_deduplicates_by_note_id(self) -> None:
        repo = SearchPipelineRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="embed"),
            rerank_service=RerankService(
                embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="rerank")
            ),
            budget_tokens=100,
        )

        result = service.search("alpha", limit=4, project="repo-a")

        self.assertEqual(result.count, 2)
        self.assertEqual([item.note.id for item in result.results], [NOTE_ID, NOTE_OTHER_ID])

    def test_search_trims_to_budget(self) -> None:
        repo = SearchPipelineRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="embed"),
            rerank_service=RerankService(
                embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="rerank")
            ),
            budget_tokens=12,
        )

        result = service.search("alpha", limit=4, project="repo-a")

        self.assertEqual(result.count, 1)
        self.assertEqual(result.results[0].note.id, NOTE_ID)

    def test_token_count_handles_punctuation_and_cjk(self) -> None:
        from anchor.application.retrieval.document_chunking import count_tokens

        self.assertEqual(count_tokens("FTS * (search)"), 2)
        self.assertGreaterEqual(count_tokens("русский текст и code_snippet()"), 3)

    def test_search_falls_back_when_embeddings_are_unavailable(self) -> None:
        repo = SearchPipelineRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FailingEmbeddingsProvider(), model="embed"),
            budget_tokens=100,
        )

        result = service.search("alpha", limit=4, project="repo-a")

        self.assertEqual(result.count, 2)
        self.assertEqual([item.note.id for item in result.results], [NOTE_ID, NOTE_OTHER_ID])

    def test_delete_removes_note_from_repository(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
        )

        service.add(title="Hello", body="one two three", source="cli")
        deleted = service.delete(NOTE_ID)

        self.assertEqual(deleted.id, NOTE_ID)
        self.assertIsNone(repo.created)
        with self.assertRaises(LookupError):
            service.get(NOTE_ID)
