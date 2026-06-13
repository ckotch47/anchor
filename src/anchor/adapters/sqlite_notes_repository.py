from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from anchor.adapters.sqlite_support import configure_connection, utc_now_iso
from anchor.application.document_chunking import DocumentChunkDraft
from anchor.application.embedding_models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.notes_models import NoteRecord, NotesSearchHit
from anchor.application.search_query import normalize_fts5_query
from anchor.application.search_scoring import combine_search_scores
from anchor.config import default_database_path


class SqliteNotesRepository:
    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or default_database_path()

    def create(
        self,
        *,
        title: str,
        body: str,
        source: str = "cli",
        source_ref: str = "",
        pinned: bool = False,
        chunks: list[DocumentChunkDraft] | None = None,
    ) -> NoteRecord:
        note_id = f"note_{uuid.uuid4().hex}"
        now = utc_now_iso()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO documents (
                    id, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (note_id, "note", title, body, source, source_ref, now, now),
            )
            connection.execute(
                """
                INSERT INTO notes (document_id, note_kind, pinned, archived_at)
                VALUES (?, ?, ?, NULL)
                """,
                (note_id, "note", int(pinned)),
            )
            self._write_chunks(connection, document_id=note_id, title=title, chunks=chunks or [], created_at=now)
            connection.commit()
            note = self.get(note_id)
            if note is None:
                raise RuntimeError("created note could not be reloaded")
            return note
        finally:
            connection.close()

    def list(self, limit: int) -> list[NoteRecord]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    n.note_kind,
                    n.pinned,
                    n.archived_at,
                    d.created_at,
                    d.updated_at
                FROM documents AS d
                JOIN notes AS n ON n.document_id = d.id
                WHERE d.document_type = 'note' AND d.deleted_at IS NULL
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]
        finally:
            connection.close()

    def get(self, note_id: str) -> NoteRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    n.note_kind,
                    n.pinned,
                    n.archived_at,
                    d.created_at,
                    d.updated_at
                FROM documents AS d
                JOIN notes AS n ON n.document_id = d.id
                WHERE d.id = ? AND d.document_type = 'note' AND d.deleted_at IS NULL
                """,
                (note_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_chunks(self, document_id: str) -> list[DocumentChunkRecord]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, document_id, chunk_index, chunk_text, token_count, created_at
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC, id ASC
                """,
                (document_id,),
            ).fetchall()
            return [self._row_to_chunk_record(row) for row in rows]
        finally:
            connection.close()

    def store_chunk_embeddings(
        self,
        embeddings: list[ChunkEmbeddingRecord],
        *,
        created_at: str,
    ) -> None:
        connection = self._connect()
        try:
            for record in embeddings:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chunk_embeddings (chunk_id, model, embedding, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (record.chunk_id, record.model, self._serialize_embedding(record.embedding), created_at),
                )
            connection.commit()
        finally:
            connection.close()

    def search(self, query: str, limit: int) -> list[NotesSearchHit]:
        match_query = normalize_fts5_query(query)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    n.note_kind,
                    n.pinned,
                    n.archived_at,
                    d.created_at,
                    d.updated_at,
                    c.id AS chunk_id,
                    1.0 / (1.0 + bm25(document_chunks_fts)) AS lexical_score,
                    snippet(document_chunks_fts, 4, '[', ']', '…', 12) AS snippet
                FROM document_chunks_fts
                JOIN document_chunks AS c ON c.id = document_chunks_fts.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN notes AS n ON n.document_id = d.id
                WHERE document_chunks_fts.document_type = ?
                  AND document_chunks_fts MATCH ?
                  AND d.document_type = ?
                  AND d.deleted_at IS NULL
                ORDER BY bm25(document_chunks_fts), d.created_at DESC
                LIMIT ?
                """,
                ("note", match_query, "note", limit),
            ).fetchall()
            return [self._row_to_search_hit(row) for row in rows]
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        configure_connection(connection, busy_timeout_ms=250)
        return connection

    def _row_to_record(self, row: sqlite3.Row) -> NoteRecord:
        return NoteRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            body=str(row["body"]),
            source=str(row["source"]),
            source_ref=str(row["source_ref"]),
            note_kind=str(row["note_kind"]),
            pinned=bool(row["pinned"]),
            archived_at=row["archived_at"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _row_to_chunk_record(self, row: sqlite3.Row) -> DocumentChunkRecord:
        return DocumentChunkRecord(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            chunk_index=int(row["chunk_index"]),
            chunk_text=str(row["chunk_text"]),
            token_count=int(row["token_count"]),
            created_at=str(row["created_at"]),
        )

    def _row_to_search_hit(self, row: sqlite3.Row) -> NotesSearchHit:
        return NotesSearchHit(
            note=self._row_to_record(row),
            chunk_id=str(row["chunk_id"]),
            score=combine_search_scores(lexical_score=float(row["lexical_score"])),
            snippet=str(row["snippet"]),
        )

    def _write_chunks(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        title: str,
        chunks: list[DocumentChunkDraft],
        created_at: str,
    ) -> None:
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"chunk_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, chunk_index, chunk_text, token_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, chunk.chunk_index if chunk.chunk_index >= 0 else chunk_index, chunk.chunk_text, chunk.token_count, created_at),
            )
            connection.execute(
                """
                INSERT INTO document_chunks_fts (document_type, document_id, chunk_id, title, chunk_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("note", document_id, chunk_id, title, chunk.chunk_text),
            )

    @staticmethod
    def _serialize_embedding(embedding: list[float]) -> bytes:
        return json.dumps(embedding, separators=(",", ":")).encode("utf-8")
