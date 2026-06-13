from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.application.embeddings.models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.notes.models import NoteRecord, NotesSearchCandidate, NotesSearchHit
from anchor.application.retrieval.document_chunking import DocumentChunkDraft
from anchor.application.retrieval.search_query import normalize_fts5_query
from anchor.application.retrieval.search_scoring import combine_search_scores, cosine_similarity


class SqliteNotesRepository(SqliteRepositoryBase):
    EMBEDDING_INDEX_TYPE = "note_embeddings"

    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

    def create(
        self,
        *,
        title: str,
        body: str,
        source: str = "cli",
        source_ref: str = "",
        pinned: bool = False,
        project: str,
        metatags: dict[str, object] | None = None,
        chunks: list[DocumentChunkDraft] | None = None,
    ) -> NoteRecord:
        note_id = f"note_{uuid.uuid4().hex}"
        now = utc_now_iso()
        serialized_metatags = self._serialize_metatags(metatags or {})
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, project, metatags, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (note_id, project, serialized_metatags, "note", title, body, source, source_ref, now, now),
            )
            connection.execute(
                """
                INSERT INTO notes (document_id, project, metatags, note_kind, pinned, archived_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (note_id, project, serialized_metatags, "note", int(pinned)),
            )
            self._write_chunks(
                connection,
                document_id=note_id,
                title=title,
                project=project,
                metatags=serialized_metatags,
                chunks=chunks or [],
                created_at=now,
            )
            connection.commit()
        self.enqueue_embedding_index(note_id)
        note = self.get(note_id, project=project)
        if note is None:
            raise RuntimeError("created note could not be reloaded")
        return note

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
        chunks: list[DocumentChunkDraft] | None = None,
    ) -> NoteRecord | None:
        current = self.get(note_id, project=project)
        if current is None:
            return None
        updated_title = title if title is not None else current.title
        updated_body = body if body is not None else current.body
        updated_source = source if source is not None else current.source
        updated_source_ref = source_ref if source_ref is not None else current.source_ref
        updated_pinned = current.pinned if pinned is None else pinned
        updated_metatags = metatags if metatags is not None else current.metatags
        serialized_metatags = self._serialize_metatags(updated_metatags)
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET title = ?, body = ?, source = ?, source_ref = ?, metatags = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'note' AND deleted_at IS NULL
                """,
                (
                    updated_title,
                    updated_body,
                    updated_source,
                    updated_source_ref,
                    serialized_metatags,
                    now,
                    note_id,
                    project,
                ),
            )
            connection.execute(
                """
                UPDATE notes
                SET metatags = ?, pinned = ?
                WHERE document_id = ? AND project = ?
                """,
                (serialized_metatags, int(updated_pinned), note_id, project),
            )
            if chunks is not None:
                connection.execute(
                    """
                    DELETE FROM document_chunks_fts
                    WHERE document_type = 'note' AND document_id = ?
                    """,
                    (note_id,),
                )
                connection.execute(
                    """
                    DELETE FROM chunk_embeddings
                    WHERE chunk_id IN (
                        SELECT id
                        FROM document_chunks
                        WHERE document_id = ?
                    )
                    """,
                    (note_id,),
                )
                connection.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE document_id = ?
                    """,
                    (note_id,),
                )
                self._write_chunks(
                    connection,
                    document_id=note_id,
                    title=updated_title,
                    project=project,
                    metatags=serialized_metatags,
                    chunks=chunks,
                    created_at=now,
                )
            connection.commit()
        self.enqueue_embedding_index(note_id)
        updated = self.get(note_id, project=project)
        if updated is None:
            raise RuntimeError("updated note could not be reloaded")
        return updated

    def delete(self, note_id: str, *, project: str) -> NoteRecord | None:
        current = self.get(note_id, project=project)
        if current is None:
            return None
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'note' AND deleted_at IS NULL
                """,
                (now, now, note_id, project),
            )
            connection.execute(
                """
                UPDATE notes
                SET archived_at = ?
                WHERE document_id = ? AND project = ?
                """,
                (now, note_id, project),
            )
            connection.execute(
                """
                DELETE FROM document_chunks_fts
                WHERE document_type = 'note' AND document_id = ?
                """,
                (note_id,),
            )
            connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT id
                    FROM document_chunks
                    WHERE document_id = ?
                )
                """,
                (note_id,),
            )
            connection.execute(
                """
                DELETE FROM document_chunks
                WHERE document_id = ?
                """,
                (note_id,),
            )
            connection.commit()
        return current

    def list(self, limit: int, *, project: str) -> list[NoteRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
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
                WHERE d.project = ? AND d.document_type = 'note' AND d.deleted_at IS NULL
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT ?
                """,
                (project, limit),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get(self, note_id: str, *, project: str) -> NoteRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
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
                WHERE d.id = ? AND d.project = ? AND d.document_type = 'note' AND d.deleted_at IS NULL
                """,
                (note_id, project),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_chunks(self, document_id: str) -> list[DocumentChunkRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, document_id, project, metatags, chunk_index, chunk_text, token_count, created_at
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC, id ASC
                """,
                (document_id,),
            ).fetchall()
            return [self._row_to_chunk_record(row) for row in rows]

    def store_chunk_embeddings(
        self,
        embeddings: list[ChunkEmbeddingRecord],
        *,
        project: str,
        metatags: str,
        created_at: str,
    ) -> None:
        with self._connect() as connection:
            for record in embeddings:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chunk_embeddings (chunk_id, project, metatags, model, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.chunk_id,
                        project,
                        metatags,
                        record.model,
                        self._serialize_embedding(record.embedding),
                        created_at,
                    ),
                )
            connection.commit()

    def enqueue_embedding_index(self, document_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO index_states (
                    entity_type, entity_id, index_type, state, indexed_at, stale_since, last_error
                )
                VALUES (?, ?, ?, 'pending', NULL, ?, NULL)
                ON CONFLICT(entity_type, entity_id, index_type)
                DO UPDATE SET
                    state = 'pending',
                    stale_since = excluded.stale_since,
                    last_error = NULL
                """,
                ("document", document_id, self.EMBEDDING_INDEX_TYPE, utc_now_iso()),
            )
            connection.commit()

    def pending_embedding_documents(self, *, project: str, limit: int = 8) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT entity_id
                FROM index_states
                WHERE entity_type = 'document'
                  AND index_type = ?
                  AND state IN ('pending', 'stale')
                  AND entity_id IN (
                      SELECT id
                      FROM documents
                      WHERE project = ? AND deleted_at IS NULL AND document_type = 'note'
                  )
                ORDER BY COALESCE(stale_since, indexed_at) ASC, entity_id ASC
                LIMIT ?
                """,
                (self.EMBEDDING_INDEX_TYPE, project, limit),
            ).fetchall()
            return [str(row["entity_id"]) for row in rows]

    def mark_embedding_index_ready(self, document_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO index_states (
                    entity_type, entity_id, index_type, state, indexed_at, stale_since, last_error
                )
                VALUES (?, ?, ?, 'ready', ?, NULL, NULL)
                ON CONFLICT(entity_type, entity_id, index_type)
                DO UPDATE SET
                    state = 'ready',
                    indexed_at = excluded.indexed_at,
                    stale_since = NULL,
                    last_error = NULL
                """,
                ("document", document_id, self.EMBEDDING_INDEX_TYPE, utc_now_iso()),
            )
            connection.commit()

    def mark_embedding_index_error(self, document_id: str, *, last_error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO index_states (
                    entity_type, entity_id, index_type, state, indexed_at, stale_since, last_error
                )
                VALUES (?, ?, ?, 'error', NULL, ?, ?)
                ON CONFLICT(entity_type, entity_id, index_type)
                DO UPDATE SET
                    state = 'error',
                    stale_since = excluded.stale_since,
                    last_error = excluded.last_error
                """,
                ("document", document_id, self.EMBEDDING_INDEX_TYPE, utc_now_iso(), last_error),
            )
            connection.commit()

    def search(self, query: str, limit: int, *, project: str) -> list[NotesSearchHit]:
        candidates = self.search_lexical_candidates(query=query, limit=limit, project=project)
        return [
            NotesSearchHit(note=candidate.note, chunk_id=candidate.chunk_id, score=candidate.lexical_score, snippet=candidate.snippet)
            for candidate in candidates
        ]

    def search_lexical_candidates(self, query: str, limit: int, *, project: str) -> list[NotesSearchCandidate]:
        match_query = normalize_fts5_query(query)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
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
                    c.chunk_text,
                    c.token_count,
                    1.0 / (1.0 + bm25(document_chunks_fts)) AS lexical_score,
                    snippet(document_chunks_fts, 4, '[', ']', '…', 12) AS snippet
                FROM document_chunks_fts
                JOIN document_chunks AS c ON c.id = document_chunks_fts.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN notes AS n ON n.document_id = d.id
                WHERE document_chunks_fts.document_type = ?
                  AND document_chunks_fts MATCH ?
                  AND d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                ORDER BY bm25(document_chunks_fts), d.created_at DESC
                LIMIT ?
                """,
                ("note", match_query, "note", project, limit),
            ).fetchall()
            return [self._row_to_search_candidate(row) for row in rows]

    def search_vector_candidates(
        self,
        query_embedding: list[float],
        limit: int,
        *,
        project: str,
    ) -> list[NotesSearchCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
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
                    c.chunk_text,
                    c.token_count,
                    ce.embedding
                FROM chunk_embeddings AS ce
                JOIN document_chunks AS c ON c.id = ce.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN notes AS n ON n.document_id = d.id
                WHERE d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                """,
                ("note", project),
            ).fetchall()
            candidates: list[NotesSearchCandidate] = []
            for row in rows:
                embedding = self._deserialize_embedding(row["embedding"])
                vector_score = cosine_similarity(query_embedding, embedding)
                candidates.append(
                    NotesSearchCandidate(
                        note=self._row_to_record(row),
                        chunk_id=str(row["chunk_id"]),
                        snippet=self._build_snippet(str(row["chunk_text"])),
                        token_count=int(row["token_count"]),
                        vector_score=vector_score,
                    )
                )
            candidates.sort(
                key=lambda item: combine_search_scores(
                    lexical_score=item.lexical_score,
                    vector_score=item.vector_score,
                ),
                reverse=True,
            )
            return candidates[:limit]
        

    def _row_to_record(self, row: sqlite3.Row) -> NoteRecord:
        return NoteRecord(
            id=str(row["id"]),
            project=str(row["project"]),
            metatags=self._deserialize_metatags(row["metatags"]),
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
            project=str(row["project"]),
            metatags=self._deserialize_metatags(row["metatags"]),
            chunk_index=int(row["chunk_index"]),
            chunk_text=str(row["chunk_text"]),
            token_count=int(row["token_count"]),
            created_at=str(row["created_at"]),
        )

    def _row_to_search_candidate(self, row: sqlite3.Row) -> NotesSearchCandidate:
        return NotesSearchCandidate(
            note=self._row_to_record(row),
            chunk_id=str(row["chunk_id"]),
            snippet=str(row["snippet"]),
            token_count=int(row["token_count"]),
            lexical_score=float(row["lexical_score"]),
        )

    def _write_chunks(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        title: str,
        project: str,
        metatags: str,
        chunks: list[DocumentChunkDraft],
        created_at: str,
    ) -> None:
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"chunk_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO document_chunks (
                    id, document_id, project, metatags, chunk_index, chunk_text, token_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    project,
                    metatags,
                    chunk.chunk_index if chunk.chunk_index >= 0 else chunk_index,
                    chunk.chunk_text,
                    chunk.token_count,
                    created_at,
                ),
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

    @staticmethod
    def _deserialize_embedding(raw_value: object) -> list[float]:
        if isinstance(raw_value, (bytes, bytearray)):
            raw_text = raw_value.decode("utf-8")
        elif isinstance(raw_value, str):
            raw_text = raw_value
        else:
            return []
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _build_snippet(chunk_text: str, max_words: int = 12) -> str:
        words = chunk_text.split()
        if len(words) <= max_words:
            return chunk_text
        return " ".join(words[:max_words]) + "…"

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _deserialize_metatags(raw_value: object) -> dict[str, object]:
        if raw_value in (None, ""):
            return {}
        if isinstance(raw_value, dict):
            return raw_value
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}
