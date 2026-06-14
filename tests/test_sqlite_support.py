from __future__ import annotations

import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_support import sqlite_write_lock


class SqliteSupportTest(unittest.TestCase):
    def test_uuid7_str_generates_uuidv7(self) -> None:
        value = uuid.UUID(uuid7_str())

        self.assertEqual(value.version, 7)
        self.assertEqual(value.variant, uuid.RFC_4122)

    def test_sqlite_write_lock_blocks_until_released(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "anchor.sqlite3"
            entered = threading.Event()
            finished = threading.Event()

            def worker() -> None:
                with sqlite_write_lock(database_path):
                    entered.set()
                    finished.set()

            with sqlite_write_lock(database_path):
                thread = threading.Thread(target=worker)
                thread.start()
                self.assertFalse(entered.wait(timeout=0.2))
                self.assertFalse(finished.is_set())

            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())
            self.assertTrue(entered.is_set())
            self.assertTrue(finished.is_set())
