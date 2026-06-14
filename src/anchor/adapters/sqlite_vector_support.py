from __future__ import annotations

import sqlite3
from functools import lru_cache
from importlib import resources

VECTOR_PYTHON_FALLBACK_LIMIT = 10_000


@lru_cache(maxsize=1)
def sqlite_vector_extension_path() -> str | None:
    try:
        extension_path = resources.files("sqlite_vector.binaries") / "vector"
    except Exception:
        return None
    return str(extension_path)


def try_load_sqlite_vector_extension(connection: sqlite3.Connection) -> bool:
    extension_path = sqlite_vector_extension_path()
    if extension_path is None:
        return False
    try:
        connection.enable_load_extension(True)
        connection.load_extension(extension_path)
        return True
    except Exception:
        return False
    finally:
        try:
            connection.enable_load_extension(False)
        except Exception:
            pass


def ensure_vector_index(connection: sqlite3.Connection, *, table: str, column: str, dimension: int) -> bool:
    if dimension <= 0:
        return False
    try:
        connection.execute(
            "SELECT vector_init(?, ?, ?)",
            (table, column, f"dimension={dimension},type=FLOAT32,distance=COSINE"),
        )
    except Exception:
        return False
    return True


def initialize_chunk_embeddings_vector(connection: sqlite3.Connection, dimension: int) -> bool:
    return ensure_vector_index(connection, table="chunk_embeddings", column="embedding", dimension=dimension)


def chunk_embeddings_project_count(connection: sqlite3.Connection, *, project: str) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM chunk_embeddings
        WHERE project = ?
        """,
        (project,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def require_vector_extension_for_large_python_fallback(
    connection: sqlite3.Connection,
    *,
    project: str,
    threshold: int = VECTOR_PYTHON_FALLBACK_LIMIT,
) -> None:
    if chunk_embeddings_project_count(connection, project=project) <= threshold:
        return
    raise RuntimeError(
        "SQLite vector extension is unavailable and Python fallback is disabled above "
        f"{threshold} embeddings. Install sqliteai-vector to enable vector search."
    )


def cosine_distance_to_score(distance: float) -> float:
    return 1.0 - distance
