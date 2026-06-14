from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.adapters.sqlite_vector_support import (
    cosine_distance_to_score,
    ensure_vector_index,
    require_vector_extension_for_large_python_fallback,
    try_load_sqlite_vector_extension,
)
from anchor.application.embeddings.models import ChunkEmbeddingRecord
from anchor.application.files.chunking import FileChunkDraft
from anchor.application.files.models import (
    FileChunkRecord,
    FileIndexDraft,
    FileListItem,
    FileSearchCandidate,
    FileSearchHit,
    IndexedFileRecord,
)
from anchor.application.retrieval.compact_items import compact_file_item
from anchor.application.retrieval.search_query import normalize_fts5_query
from anchor.application.retrieval.search_scoring import combine_search_scores, cosine_similarity


class SqliteFilesRepository(SqliteRepositoryBase):
    EMBEDDING_INDEX_TYPE = "file_embeddings"

    def __init__(self, database_path: Path | None = None, *, vector_dimension: int | None = None) -> None:
        super().__init__(database_path=database_path, vector_dimension=vector_dimension)

    def upsert_file(
        self,
        *,
        document_id: str,
        project: str,
        path: str,
        root_path: str,
        language: str,
        metatags: dict[str, object],
        file_size: int,
        content_hash: str,
        mtime_ns: int,
        chunks: list[FileChunkDraft],
    ) -> IndexedFileRecord:
        now = utc_now_iso()
        self.upsert_files(
            [
                FileIndexDraft(
                    document_id=document_id,
                    project=project,
                    path=path,
                    root_path=root_path,
                    language=language,
                    metatags=metatags,
                    file_size=file_size,
                    content_hash=content_hash,
                    mtime_ns=mtime_ns,
                    chunks=chunks,
                )
            ]
        )
        return self.get(document_id, project=project) or IndexedFileRecord(
            id=document_id,
            project=project,
            metatags=metatags,
            path=path,
            root_path=root_path,
            language=language,
            file_size=file_size,
            content_hash=content_hash,
            mtime_ns=mtime_ns,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    def upsert_files(self, files: list[FileIndexDraft]) -> None:
        if not files:
            return
        now = utc_now_iso()
        with self._connect() as connection:
            for file in files:
                self._upsert_file_in_connection(connection, file, now=now)
            connection.commit()

    def delete(self, document_id: str, *, project: str) -> IndexedFileRecord | None:
        current = self.get(document_id, project=project)
        if current is None:
            return None
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'file' AND deleted_at IS NULL
                """,
                (now, now, document_id, project),
            )
            connection.execute(
                """
                UPDATE indexed_files
                SET deleted_at = ?, updated_at = ?
                WHERE document_id = ? AND project = ?
                """,
                (now, now, document_id, project),
            )
            connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT id
                    FROM file_chunks
                    WHERE document_id = ?
                )
                """,
                (document_id,),
            )
            connection.execute("DELETE FROM file_chunks_fts WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM file_chunks WHERE document_id = ?", (document_id,))
            connection.commit()
        return current

    def get(self, document_id: str, *, project: str) -> IndexedFileRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, project, path, root_path, language, metatags, file_size, content_hash, mtime_ns,
                       created_at, updated_at, deleted_at
                FROM indexed_files
                WHERE document_id = ? AND project = ? AND deleted_at IS NULL
                """,
                (document_id, project),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_path(self, *, project: str, path: str) -> IndexedFileRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, project, path, root_path, language, metatags, file_size, content_hash, mtime_ns,
                       created_at, updated_at, deleted_at
                FROM indexed_files
                WHERE project = ? AND path = ? AND deleted_at IS NULL
                """,
                (project, path),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_indexed_files(
        self,
        *,
        project: str,
        root_path: str | None = None,
        root_paths: list[str] | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
        cursor_path: str | None = None,
        cursor_id: str | None = None,
        limit: int | None = None,
    ) -> list[IndexedFileRecord]:
        if root_path is not None and root_paths is not None:
            raise ValueError("list_indexed_files accepts either root_path or root_paths, not both")
        clauses = ["project = ?", "deleted_at IS NULL"]
        params: list[Any] = [project]
        if root_path is not None:
            clauses.append("root_path = ?")
            params.append(root_path)
        elif root_paths is not None:
            if not root_paths:
                return []
            placeholders = ", ".join("?" for _ in root_paths)
            clauses.append(f"root_path IN ({placeholders})")
            params.extend(root_paths)
        if language is not None:
            clauses.append("language = ?")
            params.append(language)
        if path_prefix is not None:
            lower_bound, upper_bound = self._path_prefix_bounds(path_prefix)
            if lower_bound is None or upper_bound is None:
                clauses.append("path LIKE ? ESCAPE '\\'")
                params.append(f"{self._escape_like(path_prefix)}%")
            else:
                clauses.append("path >= ?")
                clauses.append("path < ?")
                params.extend([lower_bound, upper_bound])
        if cursor_id is not None:
            clauses.append("document_id > ?")
            params.append(cursor_id)
        query = (
            "SELECT document_id, project, path, root_path, language, metatags, file_size, content_hash, mtime_ns, "
            "created_at, updated_at, deleted_at "
            "FROM indexed_files "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY document_id ASC"
        )
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_chunks(self, document_id: str) -> list[FileChunkRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, document_id, project, path, root_path, language, chunk_index, start_line, end_line,
                       chunk_text, token_count, created_at
                FROM file_chunks
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
                      WHERE project = ? AND deleted_at IS NULL AND document_type = 'file'
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

    def search(
        self,
        query: str,
        limit: int,
        *,
        project: str,
        root_path: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> list[FileSearchHit]:
        candidates = self.search_lexical_candidates(
            query=query,
            limit=limit,
            project=project,
            root_path=root_path,
            language=language,
            path_prefix=path_prefix,
        )
        return [
            FileSearchHit(
                file=candidate.file,
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

    def search_lexical_candidates(
        self,
        query: str,
        limit: int,
        *,
        project: str,
        root_path: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> list[FileSearchCandidate]:
        match_query = normalize_fts5_query(query)
        filters_sql, filter_params = self._file_filter_clauses(
            root_path=root_path, language=language, path_prefix=path_prefix
        )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    f.document_id,
                    f.project,
                    f.path,
                    f.root_path,
                    f.language,
                    f.file_size,
                    f.content_hash,
                    f.mtime_ns,
                    f.metatags,
                    f.created_at,
                    f.updated_at,
                    c.id AS chunk_id,
                    c.chunk_text,
                    1.0 / (1.0 + abs(bm25(file_chunks_fts))) AS lexical_score,
                    snippet(file_chunks_fts, 4, '[', ']', '…', 12) AS snippet
                FROM file_chunks_fts
                JOIN file_chunks AS c ON c.id = file_chunks_fts.chunk_id
                JOIN indexed_files AS f ON f.document_id = c.document_id
                JOIN documents AS d ON d.id = c.document_id
                WHERE file_chunks_fts.document_type = ?
                  AND file_chunks_fts MATCH ?
                  AND d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                  """
                + filters_sql
                + """
                ORDER BY bm25(file_chunks_fts), f.updated_at DESC
                LIMIT ?
                """,
                ("file", match_query, "file", project, *filter_params, limit),
            ).fetchall()
        return [
            FileSearchCandidate(
                file=compact_file_item(
                    FileListItem(
                        id=str(row["document_id"]),
                        path=str(row["path"]),
                        root_path=str(row["root_path"]),
                        language=str(row["language"]),
                        file_size=int(row["file_size"]),
                    )
                ),
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
        root_path: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> list[FileSearchCandidate]:
        filters_sql, filter_params = self._file_filter_clauses(
            root_path=root_path, language=language, path_prefix=path_prefix
        )
        with self._connect() as connection:
            vector_extension_loaded = try_load_sqlite_vector_extension(connection)
            if vector_extension_loaded and ensure_vector_index(
                connection, table="chunk_embeddings", column="embedding", dimension=len(query_embedding)
            ):
                rows = connection.execute(
                    """
                    SELECT
                        f.document_id,
                        f.project,
                        f.path,
                        f.root_path,
                        f.language,
                        f.file_size,
                        f.metatags,
                        f.created_at,
                        f.updated_at,
                        c.id AS chunk_id,
                        c.chunk_text,
                        c.token_count,
                        v.distance AS vector_distance
                    FROM vector_full_scan('chunk_embeddings', 'embedding', vector_as_f32(?)) AS v
                    JOIN chunk_embeddings AS ce ON ce.rowid = v.rowid
                    JOIN file_chunks AS c ON c.id = ce.chunk_id
                    JOIN indexed_files AS f ON f.document_id = c.document_id
                    JOIN documents AS d ON d.id = c.document_id
                    WHERE d.document_type = ?
                      AND d.project = ?
                      AND d.deleted_at IS NULL
                      """
                    + filters_sql
                    + """
                    ORDER BY v.distance ASC
                    LIMIT ?
                    """,
                    (json.dumps(query_embedding, separators=(",", ":")), "file", project, *filter_params, limit),
                ).fetchall()
                candidates = [
                    FileSearchCandidate(
                        file=compact_file_item(
                            FileListItem(
                                id=str(row["document_id"]),
                                path=str(row["path"]),
                                root_path=str(row["root_path"]),
                                language=str(row["language"]),
                                file_size=int(row["file_size"]),
                            )
                        ),
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
                    f.document_id,
                    f.project,
                    f.path,
                    f.root_path,
                    f.language,
                    f.file_size,
                    f.metatags,
                    f.created_at,
                    f.updated_at,
                    c.id AS chunk_id,
                    c.chunk_text,
                    c.token_count,
                    ce.embedding
                FROM chunk_embeddings AS ce
                JOIN file_chunks AS c ON c.id = ce.chunk_id
                JOIN indexed_files AS f ON f.document_id = c.document_id
                JOIN documents AS d ON d.id = c.document_id
                WHERE d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                  """
                + filters_sql
                + """
                """,
                ("file", project, *filter_params),
            ).fetchall()
        candidates: list[FileSearchCandidate] = []
        for row in rows:
            embedding = self._deserialize_embedding(row["embedding"])
            vector_score = cosine_similarity(query_embedding, embedding)
            candidates.append(
                FileSearchCandidate(
                    file=compact_file_item(
                        FileListItem(
                            id=str(row["document_id"]),
                            path=str(row["path"]),
                            root_path=str(row["root_path"]),
                            language=str(row["language"]),
                            file_size=int(row["file_size"]),
                        )
                    ),
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

    def file_chunks_for_document(self, document_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_text
                FROM file_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC, id ASC
                """,
                (document_id,),
            ).fetchall()
        return [str(row["chunk_text"]) for row in rows]

    @staticmethod
    def _build_snippet(chunk_text: str, max_words: int = 12) -> str:
        words = chunk_text.split()
        return " ".join(words[:max_words])

    def _row_to_record(self, row: sqlite3.Row) -> IndexedFileRecord:
        return IndexedFileRecord(
            id=str(row["document_id"]),
            project=str(row["project"]),
            metatags=self._deserialize_metatags(row["metatags"]),
            path=str(row["path"]),
            root_path=str(row["root_path"]),
            language=str(row["language"]),
            file_size=int(row["file_size"]),
            content_hash=str(row["content_hash"]),
            mtime_ns=int(row["mtime_ns"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            deleted_at=row["deleted_at"],
        )

    def _row_to_chunk_record(self, row: sqlite3.Row) -> FileChunkRecord:
        return FileChunkRecord(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            project=str(row["project"]),
            path=str(row["path"]),
            root_path=str(row["root_path"]),
            language=str(row["language"]),
            chunk_index=int(row["chunk_index"]),
            start_line=int(row["start_line"]),
            end_line=int(row["end_line"]),
            chunk_text=str(row["chunk_text"]),
            token_count=int(row["token_count"]),
            created_at=str(row["created_at"]),
        )

    def _upsert_file_in_connection(self, connection: sqlite3.Connection, file: FileIndexDraft, *, now: str) -> None:
        serialized_metatags = self._serialize_metatags(file.metatags)
        title = Path(file.path).name
        connection.execute(
            """
            INSERT INTO documents (
                id, project, metatags, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, 'file', ?, ?, 'filesystem', ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                project = excluded.project,
                metatags = excluded.metatags,
                document_type = 'file',
                title = excluded.title,
                body = excluded.body,
                source = excluded.source,
                source_ref = excluded.source_ref,
                updated_at = excluded.updated_at,
                deleted_at = NULL
            """,
            (file.document_id, file.project, serialized_metatags, title, file.path, file.path, now, now),
        )
        connection.execute(
            """
            INSERT INTO indexed_files (
                document_id, project, path, root_path, language, metatags, file_size,
                content_hash, mtime_ns, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(document_id) DO UPDATE SET
                project = excluded.project,
                path = excluded.path,
                root_path = excluded.root_path,
                language = excluded.language,
                metatags = excluded.metatags,
                file_size = excluded.file_size,
                content_hash = excluded.content_hash,
                mtime_ns = excluded.mtime_ns,
                updated_at = excluded.updated_at,
                deleted_at = NULL
            """,
            (
                file.document_id,
                file.project,
                file.path,
                file.root_path,
                file.language,
                serialized_metatags,
                file.file_size,
                file.content_hash,
                file.mtime_ns,
                now,
                now,
            ),
        )
        connection.execute(
            """
            DELETE FROM chunk_embeddings
            WHERE chunk_id IN (
                SELECT id
                FROM file_chunks
                WHERE document_id = ?
            )
            """,
            (file.document_id,),
        )
        connection.execute("DELETE FROM file_chunks_fts WHERE document_id = ?", (file.document_id,))
        connection.execute("DELETE FROM file_chunks WHERE document_id = ?", (file.document_id,))
        for chunk in file.chunks:
            chunk_id = uuid7_str()
            connection.execute(
                """
                INSERT INTO file_chunks (
                    id, document_id, project, path, root_path, language, chunk_index,
                    start_line, end_line, chunk_text, token_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    file.document_id,
                    file.project,
                    file.path,
                    file.root_path,
                    file.language,
                    chunk.chunk_index,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.chunk_text,
                    chunk.token_count,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO file_chunks_fts (document_type, document_id, chunk_id, path, chunk_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("file", file.document_id, chunk_id, file.path, chunk.chunk_text),
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

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _path_prefix_bounds(path_prefix: str) -> tuple[str | None, str | None]:
        if not path_prefix:
            return None, None
        codepoints = [ord(char) for char in path_prefix]
        for index in range(len(codepoints) - 1, -1, -1):
            if codepoints[index] < 0x10FFFF:
                upper = "".join(chr(codepoints[pos]) for pos in range(index)) + chr(codepoints[index] + 1)
                return path_prefix, upper
        return None, None

    @classmethod
    def _file_filter_clauses(
        cls,
        *,
        root_path: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if root_path is not None:
            clauses.append("AND f.root_path = ?")
            params.append(root_path)
        if language is not None:
            clauses.append("AND f.language = ?")
            params.append(language)
        if path_prefix is not None:
            lower_bound, upper_bound = cls._path_prefix_bounds(path_prefix)
            if lower_bound is None or upper_bound is None:
                clauses.append("AND f.path LIKE ? ESCAPE '\\'")
                params.append(f"{cls._escape_like(path_prefix)}%")
            else:
                clauses.append("AND f.path >= ?")
                clauses.append("AND f.path < ?")
                params.extend([lower_bound, upper_bound])
        return ("\n" + "\n".join(clauses) if clauses else ""), params
