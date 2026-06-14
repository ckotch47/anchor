from __future__ import annotations

import sqlite3
import unittest

from anchor.adapters.sqlite_vector_support import initialize_chunk_embeddings_vector, try_load_sqlite_vector_extension


class SqliteVectorSupportTest(unittest.TestCase):
    def test_loads_extension_and_initializes_chunk_embeddings(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                """
                CREATE TABLE chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL
                )
                """
            )
            self.assertTrue(try_load_sqlite_vector_extension(connection))
            self.assertTrue(initialize_chunk_embeddings_vector(connection, 1536))
            version = connection.execute("SELECT vector_version()").fetchone()[0]

        self.assertIsInstance(version, str)
        self.assertTrue(version)
