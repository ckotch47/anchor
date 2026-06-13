from __future__ import annotations

import unittest

from anchor.application.document_chunking import DocumentChunkingService
from anchor.application.embedding_models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.embedding_service import EmbeddingService
from anchor.application.notes_models import NoteRecord
from anchor.application.notes_service import NotesService


class FakeNotesRepository:
    def __init__(self) -> None:
        self.created: NoteRecord | None = None
        self.stored_embeddings: list[ChunkEmbeddingRecord] = []

    def create(self, *, title: str, body: str, source: str, source_ref: str, pinned: bool, chunks):
        self.created = NoteRecord(
            id="note_1",
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
                chunk_index=0,
                chunk_text=chunks[0].chunk_text,
                token_count=chunks[0].token_count,
                created_at="2026-06-13T00:00:00+00:00",
            )
        ]
        return self.created

    def list(self, limit: int):  # pragma: no cover - not used in test
        return []

    def get(self, note_id: str):  # pragma: no cover - not used in test
        return self.created if self.created and self.created.id == note_id else None

    def list_chunks(self, document_id: str):
        return self._chunks if document_id == "note_1" else []

    def store_chunk_embeddings(self, embeddings, *, created_at: str):
        self.stored_embeddings.extend(embeddings)

    def search(self, query: str, limit: int):  # pragma: no cover - not used in test
        return []


class FakeEmbeddingsProvider:
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class NotesServiceTest(unittest.TestCase):
    def test_add_materializes_embeddings(self) -> None:
        repo = FakeNotesRepository()
        service = NotesService(
            repository=repo,
            chunking_service=DocumentChunkingService(),
            embedding_service=EmbeddingService(provider=FakeEmbeddingsProvider(), model="test-embed"),
        )

        note = service.add(title="Hello", body="one two three", source="cli")

        self.assertEqual(note.id, "note_1")
        self.assertEqual(len(repo.stored_embeddings), 1)
        self.assertEqual(repo.stored_embeddings[0].chunk_id, "chunk_1")
        self.assertEqual(repo.stored_embeddings[0].model, "test-embed")
        self.assertEqual(repo.stored_embeddings[0].embedding, [13.0])
