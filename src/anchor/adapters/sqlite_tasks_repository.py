from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.application.retrieval.search_query import normalize_fts5_query
from anchor.application.retrieval.search_scoring import combine_search_scores
from anchor.application.tasks.models import TaskListItem, TaskRecord, TaskSearchHit


class SqliteTasksRepository(SqliteRepositoryBase):
    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

    def create(
        self,
        *,
        title: str,
        body: str,
        source: str = "cli",
        source_ref: str = "",
        project: str,
        correlation_id: str = "",
        metatags: dict[str, object] | None = None,
        task_kind: str = "task",
        priority: int = 0,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord:
        task_id = uuid7_str()
        now = utc_now_iso()
        serialized_metatags = self._serialize_metatags(metatags or {})
        body_value = body.strip() or title
        resolved_correlation_id = correlation_id or uuid7_str()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, project, metatags, correlation_id, document_type, title, body, source, source_ref, created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    task_id,
                    project,
                    serialized_metatags,
                    resolved_correlation_id,
                    "task",
                    title,
                    body_value,
                    source,
                    source_ref,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO tasks (
                    document_id, project, metatags, task_kind, status, priority, due_at, started_at,
                    completed_at, blocked_reason, parent_document_id, blocked_by_document_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    task_id,
                    project,
                    serialized_metatags,
                    task_kind,
                    "open",
                    priority,
                    due_at,
                    parent_document_id,
                    blocked_by_document_id,
                ),
            )
            self._write_task_chunk(
                connection,
                document_id=task_id,
                title=title,
                body=body_value,
                project=project,
                metatags=serialized_metatags,
                created_at=now,
            )
            connection.commit()
            task = self.get(task_id, project=project)
            if task is None:
                raise RuntimeError("created task could not be reloaded")
            return task

    def update(
        self,
        task_id: str,
        *,
        project: str,
        title: str | None = None,
        body: str | None = None,
        source: str | None = None,
        source_ref: str | None = None,
        correlation_id: str | None = None,
        metatags: dict[str, object] | None = None,
        task_kind: str | None = None,
        priority: int | None = None,
        due_at: str | None = None,
        parent_document_id: str | None = None,
        blocked_by_document_id: str | None = None,
    ) -> TaskRecord | None:
        current = self.get(task_id, project=project)
        if current is None:
            return None
        updated_title = title if title is not None else current.title
        updated_body = body if body is not None else current.body
        updated_source = source if source is not None else current.source
        updated_source_ref = source_ref if source_ref is not None else current.source_ref
        updated_correlation_id = correlation_id if correlation_id is not None else current.correlation_id
        updated_metatags = metatags if metatags is not None else current.metatags
        updated_task_kind = task_kind if task_kind is not None else current.task_kind
        updated_priority = priority if priority is not None else current.priority
        updated_due_at = due_at if due_at is not None else current.due_at
        updated_parent_document_id = (
            parent_document_id if parent_document_id is not None else current.parent_document_id
        )
        updated_blocked_by_document_id = (
            blocked_by_document_id if blocked_by_document_id is not None else current.blocked_by_document_id
        )
        body_value = updated_body.strip() or updated_title
        serialized_metatags = self._serialize_metatags(updated_metatags)
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET title = ?, body = ?, source = ?, source_ref = ?, metatags = ?, correlation_id = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'task' AND deleted_at IS NULL
                """,
                (
                    updated_title,
                    body_value,
                    updated_source,
                    updated_source_ref,
                    serialized_metatags,
                    updated_correlation_id,
                    now,
                    task_id,
                    project,
                ),
            )
            connection.execute(
                """
                UPDATE tasks
                SET metatags = ?,
                    task_kind = ?,
                    priority = ?,
                    due_at = ?,
                    parent_document_id = ?,
                    blocked_by_document_id = ?
                WHERE document_id = ? AND project = ?
                """,
                (
                    serialized_metatags,
                    updated_task_kind,
                    updated_priority,
                    updated_due_at,
                    updated_parent_document_id,
                    updated_blocked_by_document_id,
                    task_id,
                    project,
                ),
            )
            connection.execute(
                """
                DELETE FROM document_chunks_fts
                WHERE document_type = 'task' AND document_id = ?
                """,
                (task_id,),
            )
            connection.execute(
                """
                DELETE FROM document_chunks
                WHERE document_id = ?
                """,
                (task_id,),
            )
            self._write_task_chunk(
                connection,
                document_id=task_id,
                title=updated_title,
                body=body_value,
                project=project,
                metatags=serialized_metatags,
                created_at=now,
            )
            connection.commit()
            updated = self.get(task_id, project=project)
            if updated is None:
                raise RuntimeError("updated task could not be reloaded")
            return updated

    def list(
        self,
        limit: int,
        *,
        project: str,
        full: bool = False,
        cursor_id: str | None = None,
    ) -> list[TaskListItem | TaskRecord]:
        if cursor_id is not None and not cursor_id.strip():
            raise ValueError("list cursor requires a non-empty cursor_id")
        clauses = ["d.project = ?", "d.document_type = 'task'", "d.deleted_at IS NULL"]
        params: list[object] = [project]
        if cursor_id is not None:
            clauses.append("d.id < ?")
            params.append(cursor_id)
        query = (
            """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    d.correlation_id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    t.task_kind,
                    t.status,
                    t.priority,
                    t.due_at,
                    t.started_at,
                    t.completed_at,
                    t.blocked_reason,
                    t.parent_document_id,
                    t.blocked_by_document_id,
                    d.created_at,
                    d.updated_at
                FROM documents AS d
                JOIN tasks AS t ON t.document_id = d.id
                WHERE {where_clause}
                ORDER BY d.id DESC
                LIMIT ?
                """
        ).format(where_clause=" AND ".join(clauses))
        with self._connect() as connection:
            rows = connection.execute(query, (*params, limit)).fetchall()
            return [self._row_to_record(row) if full else self._row_to_list_item(row) for row in rows]

    def get(self, task_id: str, *, project: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    d.correlation_id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    t.task_kind,
                    t.status,
                    t.priority,
                    t.due_at,
                    t.started_at,
                    t.completed_at,
                    t.blocked_reason,
                    t.parent_document_id,
                    t.blocked_by_document_id,
                    d.created_at,
                    d.updated_at
                FROM documents AS d
                JOIN tasks AS t ON t.document_id = d.id
                WHERE d.id = ? AND d.project = ? AND d.document_type = 'task' AND d.deleted_at IS NULL
                """,
                (task_id, project),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def complete(self, task_id: str, *, project: str) -> TaskRecord | None:
        current = self.get(task_id, project=project)
        if current is None:
            return None
        now = utc_now_iso()
        started_at = current.started_at or now
        with self._write_connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'task' AND deleted_at IS NULL
                """,
                (now, task_id, project),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = 'done',
                    started_at = ?,
                    completed_at = ?,
                    blocked_reason = NULL
                WHERE document_id = ? AND project = ?
                """,
                (started_at, now, task_id, project),
            )
            connection.commit()
            updated = self.get(task_id, project=project)
            if updated is None:
                raise RuntimeError("completed task could not be reloaded")
            return updated

    def delete(self, task_id: str, *, project: str) -> TaskRecord | None:
        current = self.get(task_id, project=project)
        if current is None:
            return None
        now = utc_now_iso()
        with self._write_connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND project = ? AND document_type = 'task' AND deleted_at IS NULL
                """,
                (now, now, task_id, project),
            )
            connection.execute(
                """
                DELETE FROM document_chunks_fts
                WHERE document_type = 'task' AND document_id = ?
                """,
                (task_id,),
            )
            connection.execute(
                """
                DELETE FROM document_chunks
                WHERE document_id = ?
                """,
                (task_id,),
            )
            connection.commit()
        return current

    def search(self, query: str, limit: int, *, project: str) -> list[TaskSearchHit]:
        match_query = normalize_fts5_query(query)
        self._backfill_missing_task_chunks(project=project)
        with self._write_connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.metatags,
                    d.correlation_id,
                    d.title,
                    d.body,
                    d.source,
                    d.source_ref,
                    t.task_kind,
                    t.status,
                    t.priority,
                    t.due_at,
                    t.started_at,
                    t.completed_at,
                    t.blocked_reason,
                    t.parent_document_id,
                    t.blocked_by_document_id,
                    d.created_at,
                    d.updated_at,
                    c.id AS chunk_id,
                    1.0 / (1.0 + abs(bm25(document_chunks_fts))) AS lexical_score,
                    snippet(document_chunks_fts, 4, '[', ']', '…', 12) AS snippet
                FROM document_chunks_fts
                JOIN document_chunks AS c ON c.id = document_chunks_fts.chunk_id
                JOIN documents AS d ON d.id = c.document_id
                JOIN tasks AS t ON t.document_id = d.id
                WHERE document_chunks_fts.document_type = ?
                  AND document_chunks_fts MATCH ?
                  AND d.document_type = ?
                  AND d.project = ?
                  AND d.deleted_at IS NULL
                ORDER BY bm25(document_chunks_fts), d.created_at DESC
                LIMIT ?
                """,
                ("task", match_query, "task", project, limit),
            ).fetchall()
            return [self._row_to_search_hit(row) for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=str(row["id"]),
            project=str(row["project"]),
            metatags=self._deserialize_metatags(row["metatags"]),
            correlation_id=str(row["correlation_id"]),
            title=str(row["title"]),
            body=str(row["body"]),
            source=str(row["source"]),
            source_ref=str(row["source_ref"]),
            task_kind=str(row["task_kind"]),
            status=str(row["status"]),
            priority=int(row["priority"]),
            due_at=row["due_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            blocked_reason=row["blocked_reason"],
            parent_document_id=row["parent_document_id"],
            blocked_by_document_id=row["blocked_by_document_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _row_to_list_item(self, row: sqlite3.Row) -> TaskListItem:
        return TaskListItem(
            id=str(row["id"]),
            title=str(row["title"]),
            status=str(row["status"]),
            priority=int(row["priority"]),
        )

    def _row_to_search_hit(self, row: sqlite3.Row) -> TaskSearchHit:
        return TaskSearchHit(
            task=self._row_to_list_item(row),
            chunk_id=str(row["chunk_id"]),
            score=combine_search_scores(lexical_score=float(row["lexical_score"])),
            snippet=str(row["snippet"]),
        )

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, ensure_ascii=False, separators=(",", ":"))

    def _write_task_chunk(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        title: str,
        body: str,
        project: str,
        metatags: str,
        created_at: str,
    ) -> None:
        chunk_id = uuid7_str()
        chunk_text = f"{title}\n{body}".strip()
        connection.execute(
            """
            INSERT INTO document_chunks (
                id, document_id, project, metatags, chunk_index, chunk_text, token_count, created_at
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                chunk_id,
                document_id,
                project,
                metatags,
                chunk_text,
                max(1, len(chunk_text.split())),
                created_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO document_chunks_fts (document_type, document_id, chunk_id, title, chunk_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("task", document_id, chunk_id, title, body),
        )

    def _backfill_missing_task_chunks(self, *, project: str) -> None:
        with self._write_connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.project,
                    d.title,
                    d.body,
                    d.metatags,
                    d.created_at
                FROM documents AS d
                JOIN tasks AS t ON t.document_id = d.id
                LEFT JOIN document_chunks AS c ON c.document_id = d.id
                WHERE d.project = ?
                  AND d.document_type = 'task'
                  AND d.deleted_at IS NULL
                  AND c.document_id IS NULL
                """,
                (project,),
            ).fetchall()
            for row in rows:
                self._write_task_chunk(
                    connection,
                    document_id=str(row["id"]),
                    title=str(row["title"]),
                    body=str(row["body"]),
                    project=str(row["project"]),
                    metatags=str(row["metatags"]),
                    created_at=str(row["created_at"]),
                )
            connection.commit()

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
