from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from anchor.adapters.sqlite_support import configure_connection
from anchor.adapters.sqlite_vector_support import try_load_sqlite_vector_extension
from anchor.config import default_database_path


class SqliteRepositoryBase:
    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or default_database_path()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        configure_connection(connection, busy_timeout_ms=250)
        try_load_sqlite_vector_extension(connection)
        try:
            yield connection
        finally:
            connection.close()
