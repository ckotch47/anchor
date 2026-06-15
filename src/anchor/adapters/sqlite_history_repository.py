from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_link_summaries import parse_link_summaries
from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.adapters.sqlite_vector_support import (
    cosine_distance_to_score,
    ensure_vector_index,
    require_vector_extension_for_large_python_fallback,
    try_load_sqlite_vector_extension,
)
from anchor.application.embeddings.models import ChunkEmbeddingRecord, DocumentChunkRecord
from anchor.application.history.models import HistoryListItem, HistoryRecord, HistorySearchCandidate, HistorySearchHit
from anchor.application.retrieval.document_chunking import DocumentChunkDraft
from anchor.application.retrieval.search_query import normalize_fts5_query
from anchor.application.retrieval.search_scoring import combine_search_scores, cosine_similarity


class SqliteHistoryRepository(SqliteRepositoryBase):
    EMBEDDING_INDEX_TYPE = "history_embeddings"

    def __init__(self, database_path: Path | None = None, *, vector_dimension: int | None = None) -> None:
        super().__init__(database_path=database_path, vector_dimension=vector_dimension)

    def append(
        self,
        *,
        entry_type: str,
        payload: str,
        actor: str = "agent",
        correlation_id: str = "",
        project: str,
        metatags: dict[str, object] | None = None,
        chunks: list[DocumentChunkDraft] | None = None,
    ) -> HistoryRecord:
        document_id = uuid7_str()
        now = utc_now_iso()
        serialized_metatags = self._serialize_metatags(metatags or {})
        body_value = payload.strip()
        if not body_value:
            raise ValueError("payload must not be empty")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, project, metatags, correlation_id, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, 'history', ?, ?, 'history', ?, ?, ?, NULL)
                """,
                (
                    document_id,
                    project,
                    serialized_metatags,
                    correlation_id,
                    entry_type,
                    body_value,
                    correlation_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO history_entries (
                    document_id, project, metatags, entry_type, actor, payload, correlation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, project, serialized_metatags, entry_type, actor, body_value, correlation_id),
            )
            self._write_chunks(
                connection,
                document_id=document_id,
                title=entry_type,
                project=project,
                metatags=serialized_metatags,
                chunks=chunks or [DocumentChunkDraft(chunk_index=0, chunk_text=body_value, token_count=1)],
                created_at=now,
            )
            connection.commit()
        self.enqueue_embedding_index(document_id)
        record = self.get(document_id, project=project)
        if record is None:
            raise RuntimeError("created history entry could not be reloaded")
        return record

    def get(self, document_id: str, *, project: str) -> HistoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    h.entry_type,
                    h.actor,
                    h.payload,
                    h.correlation_id,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', to_document_id, 'type', link_type, 'direction', 'out')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE from_document_id = d.id
                    ) AS outbound_links_json,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', from_document_id, 'type', link_type, 'direction', 'in')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE to_document_id = d.id
                    ) AS inbound_links_json,
                    d.created_at,
                    d.updated_at
                FROM documents AS d
                JOIN history_entries AS h ON h.document_id = d.id
                WHERE d.id = ? AND d.project = ? AND d.document_type = 'history' AND d.deleted_at IS NULL
                """,
                (document_id, project),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def update(
        self,
        document_id: str,
        *,
        project: str,
        entry_type: str | None = None,
        payload: str | None = None,
        actor: str | None = None,
        correlation_id: str | None = None,
        metatags: dict[str, object] | None = None,
        chunks: list[DocumentChunkDraft] | None = None,
    ) -> HistoryRecord | None:
        current = self.get(document_id, project=project)
        if current is None:
            return None
        updated_entry_type = entry_type if entry_type is not None else current.entry_type
        updated_payload = payload if payload is not None else current.payload
        updated_actor = actor if actor is not None else current.actor
        updated_correlation_id = correlation_id if correlation_id is not None else current.correlation_id
        updated_metatags = metatags if metatags is not None else current.metatags
        serialized_metatags = self._serialize_metatags(updated_metatags)
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET title = ?, body = ?, source_ref = ?, metatags = ?, correlation_id = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'history' AND deleted_at IS NULL
                """,
                (
                    updated_entry_type,
                    updated_payload,
                    updated_correlation_id,
                    serialized_metatags,
                    updated_correlation_id,
                    now,
                    document_id,
                    project,
                ),
            )
            connection.execute(
                """
                UPDATE history_entries
                SET project = ?, metatags = ?, entry_type = ?, actor = ?, payload = ?, correlation_id = ?
                WHERE document_id = ?
                """,
                (
                    project,
                    serialized_metatags,
                    updated_entry_type,
                    updated_actor,
                    updated_payload,
                    updated_correlation_id,
                    document_id,
                ),
            )
            if chunks is not None:
                self._purge_retrieval_rows(connection, document_id=document_id)
                self._write_chunks(
                    connection,
                    document_id=document_id,
                    title=updated_entry_type,
                    project=project,
                    metatags=serialized_metatags,
                    chunks=chunks,
                    created_at=now,
                )
            connection.commit()
        if chunks is not None:
            self.enqueue_embedding_index(document_id)
        updated = self.get(document_id, project=project)
        if updated is None:
            raise RuntimeError("updated history entry could not be reloaded")
        return updated

    def delete(self, document_id: str, *, project: str) -> HistoryRecord | None:
        current = self.get(document_id, project=project)
        if current is None:
            return None
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'history' AND deleted_at IS NULL
                """,
                (now, now, document_id, project),
            )
            self._purge_retrieval_rows(connection, document_id=document_id)
            connection.commit()
        return current

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
        with self._write_connect() as connection:
            use_vector_encoding = try_load_sqlite_vector_extension(connection)
            embedding_sql = "vector_as_f32(?)" if use_vector_encoding else "?"
            for record in embeddings:
                connection.execute(
                    f"""
                    INSERT OR REPLACE INTO chunk_embeddings (chunk_id, project, metatags, model, embedding, created_at)
                    VALUES (?, ?, ?, ?, {embedding_sql}, ?)
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
        with self._write_connect() as connection:
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
        with self._write_connect() as connection:
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
                      WHERE project = ? AND deleted_at IS NULL AND document_type = 'history'
                  )
                ORDER BY COALESCE(stale_since, indexed_at) ASC, entity_id ASC
                LIMIT ?
                """,
                (self.EMBEDDING_INDEX_TYPE, project, limit),
            ).fetchall()
        return [str(row["entity_id"]) for row in rows]

    def mark_embedding_index_ready(self, document_id: str) -> None:
        with self._write_connect() as connection:
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
        with self._write_connect() as connection:
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

    def search(self, query: str, limit: int, *, project: str) -> list[HistorySearchHit]:
        candidates = self.search_lexical_candidates(query=query, limit=limit, project=project)
        return [
            HistorySearchHit(
                history=candidate.history,
                chunk_id=candidate.chunk_id,
                score=combine_search_scores(
                    lexical_score=candidate.lexical_score,
                    vector_score=candidate.vector_score,
                    rerank_score=candidate.rerank_score,
                ),
                snippet=candidate.snippet,
            )
            for candidate in candidates[:limit]
        ]

    def search_lexical_candidates(self, query: str, limit: int, *, project: str) -> list[HistorySearchCandidate]:
        match_query = normalize_fts5_query(query)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    h.entry_type,
                    h.actor,
                    h.payload,
                    h.correlation_id,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', to_document_id, 'type', link_type, 'direction', 'out')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE from_document_id = d.id
                    ) AS outbound_links_json,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', from_document_id, 'type', link_type, 'direction', 'in')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE to_document_id = d.id
                    ) AS inbound_links_json,
                    d.created_at,
                    d.updated_at,
                    c.id AS chunk_id,
                    c.chunk_text,
                    c.token_count,
                    1.0 / (1.0 + abs(bm25(document_chunks_fts))) AS lexical_score,
                    snippet(document_chunks_fts, 4, '[', ']', '…', 12) AS snippet
                FROM document_chunks_fts
                JOIN document_chunks AS c ON c.id = document_chunks_fts.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN history_entries AS h ON h.document_id = d.id
                WHERE document_chunks_fts.document_type = ?
                  AND document_chunks_fts MATCH ?
                  AND d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                ORDER BY bm25(document_chunks_fts), d.created_at DESC
                LIMIT ?
                """,
                ("history", match_query, "history", project, limit),
            ).fetchall()
        return [
            HistorySearchCandidate(
                history=self._row_to_search_item(row),
                chunk_id=str(row["chunk_id"]),
                snippet=str(row["snippet"]),
                token_count=max(1, len(str(row["snippet"]).split())),
                lexical_score=float(row["lexical_score"]),
            )
            for row in rows
        ]

    def search_vector_candidates(
        self,
        query_embedding: list[float],
        limit: int,
        *,
        project: str,
    ) -> list[HistorySearchCandidate]:
        with self._connect() as connection:
            vector_extension_loaded = try_load_sqlite_vector_extension(connection)
            if vector_extension_loaded and ensure_vector_index(
                connection, table="chunk_embeddings", column="embedding", dimension=len(query_embedding)
            ):
                rows = connection.execute(
                    """
                    SELECT
                        d.id,
                        d.project,
                        d.metatags,
                        h.entry_type,
                        h.actor,
                        h.payload,
                        h.correlation_id,
                        d.created_at,
                        d.updated_at,
                        c.id AS chunk_id,
                        c.chunk_text,
                        c.token_count,
                        v.distance AS vector_distance
                    FROM vector_full_scan('chunk_embeddings', 'embedding', vector_as_f32(?)) AS v
                    JOIN chunk_embeddings AS ce ON ce.rowid = v.rowid
                    JOIN document_chunks AS c ON c.id = ce.chunk_id
                    JOIN documents AS d ON d.id = c.document_id
                    JOIN history_entries AS h ON h.document_id = d.id
                    WHERE d.document_type = ?
                      AND d.project = ?
                      AND d.deleted_at IS NULL
                    ORDER BY v.distance ASC
                    LIMIT ?
                    """,
                    (json.dumps(query_embedding, separators=(",", ":")), "history", project, limit),
                ).fetchall()
                candidates = [
                    HistorySearchCandidate(
                        history=self._row_to_search_item(row),
                        chunk_id=str(row["chunk_id"]),
                        snippet=self._build_snippet(str(row["chunk_text"])),
                        token_count=int(row["token_count"]),
                        vector_score=cosine_distance_to_score(float(row["vector_distance"])),
                    )
                    for row in rows
                ]
                candidates.sort(
                    key=lambda item: combine_search_scores(
                        lexical_score=item.lexical_score,
                        vector_score=item.vector_score,
                    ),
                    reverse=True,
                )
                return candidates[:limit]
            if not vector_extension_loaded:
                require_vector_extension_for_large_python_fallback(connection, project=project)
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    h.entry_type,
                    h.actor,
                    h.payload,
                    h.correlation_id,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', to_document_id, 'type', link_type, 'direction', 'out')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE from_document_id = d.id
                    ) AS outbound_links_json,
                    (
                        SELECT COALESCE(
                            json_group_array(
                                json_object('id', from_document_id, 'type', link_type, 'direction', 'in')
                            ),
                            '[]'
                        )
                        FROM document_links
                        WHERE to_document_id = d.id
                    ) AS inbound_links_json,
                    d.created_at,
                    d.updated_at,
                    c.id AS chunk_id,
                    c.chunk_text,
                    c.token_count,
                    ce.embedding
                FROM chunk_embeddings AS ce
                JOIN document_chunks AS c ON c.id = ce.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN history_entries AS h ON h.document_id = d.id
                WHERE d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                """,
                ("history", project),
            ).fetchall()
        candidates: list[HistorySearchCandidate] = []
        for row in rows:
            embedding = self._deserialize_embedding(row["embedding"])
            vector_score = cosine_similarity(query_embedding, embedding)
            candidates.append(
                HistorySearchCandidate(
                    history=self._row_to_search_item(row),
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

    @staticmethod
    def _build_snippet(chunk_text: str, max_words: int = 12) -> str:
        words = chunk_text.split()
        return " ".join(words[:max_words])

    def _row_to_record(self, row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            id=str(row["id"]),
            project=str(row["project"]),
            metatags=self._deserialize_metatags(row["metatags"]),
            entry_type=str(row["entry_type"]),
            actor=str(row["actor"]),
            payload=str(row["payload"]),
            correlation_id=str(row["correlation_id"]),
            links=self._row_to_links(row),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _row_to_search_item(self, row: sqlite3.Row) -> HistoryListItem:
        return HistoryListItem(
            id=str(row["id"]),
            project=str(row["project"]),
            entry_type=str(row["entry_type"]),
            actor=str(row["actor"]),
            correlation_id=str(row["correlation_id"]),
            links=self._row_to_links(row),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _row_to_links(row: sqlite3.Row):
        return parse_link_summaries(row["outbound_links_json"], row["inbound_links_json"])

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
            chunk_id = uuid7_str()
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
                ("history", document_id, chunk_id, title, chunk.chunk_text),
            )

    def _purge_retrieval_rows(self, connection: sqlite3.Connection, *, document_id: str) -> None:
        connection.execute(
            """
            DELETE FROM document_chunks_fts
            WHERE document_type = 'history' AND document_id = ?
            """,
            (document_id,),
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
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM document_chunks
            WHERE document_id = ?
            """,
            (document_id,),
        )
        connection.execute(
            """
            DELETE FROM index_states
            WHERE entity_type = 'document' AND entity_id = ? AND index_type = ?
            """,
            (document_id, self.EMBEDDING_INDEX_TYPE),
        )

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, ensure_ascii=False, separators=(",", ":"))

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

    @staticmethod
    def _serialize_embedding(embedding: list[float]) -> str:
        return json.dumps(embedding, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize_embedding(raw_value: object) -> list[float]:
        if raw_value in (None, ""):
            return []
        if isinstance(raw_value, list):
            return [float(value) for value in raw_value]
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                return []
            if isinstance(parsed, list):
                return [float(value) for value in parsed]
        return []
