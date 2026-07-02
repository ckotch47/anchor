from __future__ import annotations

from anchor.adapters.sqlite_repository import SqliteRepositoryBase


class SqliteProjectsRepository(SqliteRepositoryBase):
    def list_projects(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT DISTINCT project FROM (
                    SELECT project FROM documents WHERE deleted_at IS NULL
                    UNION
                    SELECT project FROM indexed_files
                )
                ORDER BY project
            """).fetchall()
            return [row["project"] for row in rows]
