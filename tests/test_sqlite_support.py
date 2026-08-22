from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from anchor.adapters.sqlite_support import (
    connect_trusted_sqlite,
    connect_trusted_sqlite_read_only,
    sqlite_write_lock,
)


class SqliteSupportTest(unittest.TestCase):
    def test_database_is_created_private_under_permissive_umask(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            database = root / "anchor.sqlite3"
            previous_umask = os.umask(0o022)
            try:
                connection = connect_trusted_sqlite(database)
            finally:
                os.umask(previous_umask)
            connection.close()

            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)

    def test_existing_database_mode_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            database = root / "anchor.sqlite3"
            database.touch(mode=0o644)
            database.chmod(0o644)

            connection = connect_trusted_sqlite(database)
            connection.close()

            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)

    def test_symlink_and_hardlink_databases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            target = root / "target.sqlite3"
            target.touch(mode=0o600)
            symlink = root / "symlink.sqlite3"
            symlink.symlink_to(target)
            hardlink = root / "hardlink.sqlite3"
            os.link(target, hardlink)

            with self.assertRaises((OSError, ValueError)):
                connect_trusted_sqlite(symlink)
            with self.assertRaises(ValueError):
                connect_trusted_sqlite(hardlink)

    def test_group_writable_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o770)

            with self.assertRaises(ValueError):
                connect_trusted_sqlite(root / "anchor.sqlite3")

    def test_read_only_connect_does_not_create_or_modify_database(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            missing = root / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                connect_trusted_sqlite_read_only(missing)
            self.assertFalse(missing.exists())

            database = root / "anchor.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE checks (value INTEGER NOT NULL)")
                connection.execute("INSERT INTO checks VALUES (1)")
                connection.commit()
            database.chmod(0o600)
            before = database.stat()

            connection = connect_trusted_sqlite_read_only(database)
            try:
                self.assertEqual(connection.execute("SELECT value FROM checks").fetchone(), (1,))
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("INSERT INTO checks VALUES (2)")
            finally:
                connection.close()

            after = database.stat()
            self.assertEqual(after.st_size, before.st_size)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            self.assertFalse(Path(f"{database}-wal").exists())
            self.assertFalse(Path(f"{database}-shm").exists())

    def test_read_only_connect_rejects_insecure_mode_without_repairing_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            database = root / "anchor.sqlite3"
            database.touch(mode=0o644)
            database.chmod(0o644)

            with self.assertRaises(ValueError):
                connect_trusted_sqlite_read_only(database)

            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o644)

    def test_sqlite_write_lock_serializes_concurrent_writers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            database = Path(raw) / "anchor.sqlite3"
            attempted = threading.Event()
            acquired = threading.Event()

            def acquire_in_thread() -> None:
                attempted.set()
                with sqlite_write_lock(database):
                    acquired.set()

            with sqlite_write_lock(database):
                worker = threading.Thread(target=acquire_in_thread)
                worker.start()
                self.assertTrue(attempted.wait(timeout=1))
                self.assertFalse(acquired.wait(timeout=0.05))

            self.assertTrue(acquired.wait(timeout=1))
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())

    def test_sqlite_write_lock_rejects_symlinks_and_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "target.lock"
            target.touch(mode=0o600)

            symlink_database = root / "symlink.sqlite3"
            Path(f"{symlink_database}.write.lock").symlink_to(target)
            with self.assertRaises((OSError, ValueError)):
                with sqlite_write_lock(symlink_database):
                    self.fail("symlink lock must not be acquired")

            hardlink_database = root / "hardlink.sqlite3"
            os.link(target, Path(f"{hardlink_database}.write.lock"))
            with self.assertRaises(ValueError):
                with sqlite_write_lock(hardlink_database):
                    self.fail("hardlink lock must not be acquired")


if __name__ == "__main__":
    unittest.main()
