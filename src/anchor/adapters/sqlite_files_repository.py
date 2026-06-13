from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.application.files.chunking import FileChunkDraft
from anchor.application.files.models import FileListItem, FileSearchHit, IndexedFileRecord
from anchor.application.retrieval.search_query import normalize_fts5_query


class SqliteFilesRepository(SqliteRepositoryBase):
    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

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
        serialized_metatags = self._serialize_metatags(metatags)
        title = Path(path).name
        with self._connect() as connection:
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
                (document_id, project, serialized_metatags, title, path, path, now, now),
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
                    document_id,
                    project,
                    path,
                    root_path,
                    language,
                    serialized_metatags,
                    file_size,
                    content_hash,
                    mtime_ns,
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM file_chunks_fts WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM file_chunks WHERE document_id = ?", (document_id,))
            for chunk in chunks:
                chunk_id = f"chunk_{uuid.uuid4().hex}"
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
                        document_id,
                        project,
                        path,
                        root_path,
                        language,
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
                    ("file", document_id, chunk_id, path, chunk.chunk_text),
                )
            connection.commit()
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

    def list_indexed_files(self, *, project: str) -> list[IndexedFileRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, project, path, root_path, language, metatags, file_size, content_hash, mtime_ns,
                       created_at, updated_at, deleted_at
                FROM indexed_files
                WHERE project = ? AND deleted_at IS NULL
                ORDER BY path ASC
                """,
                (project,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def search(self, query: str, limit: int, *, project: str) -> list[FileSearchHit]:
        candidates = self.search_lexical_candidates(query=query, limit=limit, project=project)
        return [
            FileSearchHit(
                file=FileListItem(
                    id=candidate.file.id,
                    path=candidate.file.path,
                    root_path=candidate.file.root_path,
                    language=candidate.file.language,
                    file_size=candidate.file.file_size,
                ),
                chunk_id=candidate.chunk_id,
                score=candidate.score,
                snippet=candidate.snippet,
            )
            for candidate in candidates
        ]

    def search_lexical_candidates(self, query: str, limit: int, *, project: str) -> list[FileSearchHit]:
        match_query = normalize_fts5_query(query)
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
                ORDER BY bm25(file_chunks_fts), f.updated_at DESC
                LIMIT ?
                """,
                ("file", match_query, "file", project, limit),
            ).fetchall()
        return [
            FileSearchHit(
                file=FileListItem(
                    id=str(row["document_id"]),
                    path=str(row["path"]),
                    root_path=str(row["root_path"]),
                    language=str(row["language"]),
                    file_size=int(row["file_size"]),
                ),
                chunk_id=str(row["chunk_id"]),
                score=float(row["lexical_score"]),
                snippet=str(row["snippet"]),
            )
            for row in rows
        ]

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
