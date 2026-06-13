from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def configure_connection(connection: sqlite3.Connection, busy_timeout_ms: int) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
