from __future__ import annotations

import sqlite3
from pathlib import Path

from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.application.links.models import DocumentLinkRecord


class SqliteLinksRepository(SqliteRepositoryBase):
    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

    def create(self, *, source_id: str, target_id: str, relation_type: str) -> DocumentLinkRecord:
        now = utc_now_iso()
        with self._write_connect() as connection:
            connection.execute(
                """
                INSERT INTO document_links (from_document_id, to_document_id, link_type, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(from_document_id, to_document_id, link_type)
                DO UPDATE SET created_at = excluded.created_at
                """,
                (source_id, target_id, relation_type, now),
            )
            connection.commit()
        return DocumentLinkRecord(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            created_at=now,
        )

    def list_by_source(self, source_id: str) -> list[DocumentLinkRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT from_document_id, to_document_id, link_type, created_at
                FROM document_links
                WHERE from_document_id = ?
                ORDER BY created_at DESC, to_document_id ASC
                """,
                (source_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_by_target(self, target_id: str) -> list[DocumentLinkRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT from_document_id, to_document_id, link_type, created_at
                FROM document_links
                WHERE to_document_id = ?
                ORDER BY created_at DESC, from_document_id ASC
                """,
                (target_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def delete(self, *, source_id: str, target_id: str, relation_type: str) -> bool:
        with self._write_connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM document_links
                WHERE from_document_id = ? AND to_document_id = ? AND link_type = ?
                """,
                (source_id, target_id, relation_type),
            )
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DocumentLinkRecord:
        return DocumentLinkRecord(
            source_id=str(row["from_document_id"]),
            target_id=str(row["to_document_id"]),
            relation_type=str(row["link_type"]),
            created_at=str(row["created_at"]),
        )
