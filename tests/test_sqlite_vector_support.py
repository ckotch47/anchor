from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from anchor.adapters.sqlite_vector_support import (
    initialize_chunk_embeddings_vector,
    require_vector_extension_for_large_python_fallback,
    sqlite_vector_extension_path,
    try_load_sqlite_vector_extension,
)


class SqliteVectorSupportTest(unittest.TestCase):
    def test_loads_extension_and_initializes_chunk_embeddings(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            if sqlite_vector_extension_path() is None:
                self.skipTest("sqlite vector extension unavailable in test environment")
            connection.execute(
                """
                CREATE TABLE chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL
                )
                """
            )
            if not try_load_sqlite_vector_extension(connection):
                self.skipTest("sqlite vector extension could not be loaded in test environment")
            self.assertTrue(initialize_chunk_embeddings_vector(connection, 1536))
            version = connection.execute("SELECT vector_version()").fetchone()[0]

        self.assertIsInstance(version, str)
        self.assertTrue(version)

    def test_rejects_python_fallback_for_large_embedding_sets(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                """
                CREATE TABLE chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    embedding BLOB NOT NULL
                )
                """
            )
            with patch(
                "anchor.adapters.sqlite_vector_support.chunk_embeddings_project_count",
                return_value=10_001,
            ):
                with self.assertRaises(RuntimeError) as exc_info:
                    require_vector_extension_for_large_python_fallback(connection, project="repo-a")

        self.assertIn("sqliteai-vector", str(exc_info.exception))
