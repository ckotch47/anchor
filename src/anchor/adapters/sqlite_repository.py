from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from anchor.adapters.sqlite_support import configure_connection, connect_trusted_sqlite, sqlite_write_lock
from anchor.adapters.sqlite_vector_support import initialize_chunk_embeddings_vector, try_load_sqlite_vector_extension
from anchor.config import default_database_path


class SqliteRepositoryBase:
    def __init__(self, database_path: Path | None = None, *, vector_dimension: int | None = None) -> None:
        self._database_path = database_path or default_database_path()
        self._vector_dimension = vector_dimension

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = connect_trusted_sqlite(self._database_path)
        connection.row_factory = sqlite3.Row
        configure_connection(connection, busy_timeout_ms=250, database_path=self._database_path)
        try_load_sqlite_vector_extension(connection)
        if self._vector_dimension is not None:
            initialize_chunk_embeddings_vector(connection, self._vector_dimension)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_connect(self) -> Iterator[sqlite3.Connection]:
        with sqlite_write_lock(self._database_path):
            with self._connect() as connection:
                yield connection
