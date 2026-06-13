from __future__ import annotations

import unittest

from anchor.application.embeddings.models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.models import NoteRecord, NotesSearchCandidate
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_service import RerankService


class FakeNotesRepository:
    def __init__(self) -> None:
        self.created: NoteRecord | None = None
        self._chunks = []
        self.stored_embeddings: list[ChunkEmbeddingRecord] = []

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
            id="note_1",
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
                id="chunk_1",
                document_id="note_1",
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
                    id="chunk_1",
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
        return self._chunks if document_id == "note_1" else []

    def store_chunk_embeddings(self, embeddings, *, project: str, metatags: str, created_at: str):
        self.stored_embeddings.extend(embeddings)

    def search(self, query: str, limit: int, *, project: str):  # pragma: no cover - not used in test
        return []


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
            id="note_1",
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
            id="note_2",
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
                note=self.note_one,
                chunk_id="chunk_lex_1",
                snippet="alpha lexical snippet with many words to consume budget",
                token_count=8,
                lexical_score=0.95,
            ),
            NotesSearchCandidate(
                note=self.note_two,
                chunk_id="chunk_lex_2",
                snippet="beta lexical snippet that will be trimmed later",
                token_count=8,
                lexical_score=0.85,
            ),
        ][:limit]

    def search_vector_candidates(self, query_embedding: list[float], limit: int, *, project: str):
        del query_embedding, project
        return [
            NotesSearchCandidate(
                note=self.note_one,
                chunk_id="chunk_vec_1",
                snippet="alpha vector snippet with many words to consume budget",
                token_count=8,
                vector_score=0.99,
            ),
            NotesSearchCandidate(
                note=self.note_two,
                chunk_id="chunk_vec_2",
                snippet="beta vector snippet that will be trimmed later",
                token_count=8,
                vector_score=0.80,
            ),
        ][:limit]


class NotesServiceTest(unittest.TestCase):
    def test_add_materializes_embeddings(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        note = service.add(title="Hello", body="one two three", source="cli")

        self.assertEqual(note.id, "note_1")
        self.assertEqual(len(repo.stored_embeddings), 1)
        self.assertEqual(repo.stored_embeddings[0].chunk_id, "chunk_1")
        self.assertEqual(repo.stored_embeddings[0].model, "test-embed")
        self.assertEqual(repo.stored_embeddings[0].embedding, [13.0])

    def test_update_rebuilds_chunks_and_embeddings(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        service.add(title="Hello", body="one two three", source="cli")
        updated = service.update("note_1", title="Hello again", body="four five six")

        self.assertEqual(updated.title, "Hello again")
        self.assertEqual(updated.body, "four five six")
        self.assertEqual(len(repo.stored_embeddings), 2)
        self.assertEqual(repo.stored_embeddings[-1].chunk_id, "chunk_1")

    def test_update_rejects_empty_payload(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            project="workspace",
        )

        service.add(title="Hello", body="one two three", source="cli")

        with self.assertRaises(ValueError):
            service.update("note_1")

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
        self.assertEqual([item.note.id for item in result.results], ["note_1", "note_2"])

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
        self.assertEqual(result.results[0].note.id, "note_1")

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
        self.assertEqual([item.note.id for item in result.results], ["note_1", "note_2"])
