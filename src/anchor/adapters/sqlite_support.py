from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]


def configure_connection(
    connection: sqlite3.Connection,
    busy_timeout_ms: int,
    *,
    database_path: Path | None = None,
) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    if database_path is not None:
        secure_sqlite_files(database_path)


def connect_trusted_sqlite(database_path: Path) -> sqlite3.Connection:
    parent = database_path.parent
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent_metadata = os.lstat(parent)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent.is_symlink()
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise ValueError("SQLite parent must be a trusted private directory")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(database_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ValueError("SQLite database must be a trusted regular file")
        os.fchmod(descriptor, 0o600)
        connection = sqlite3.connect(database_path)
        current = os.lstat(database_path)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            connection.close()
            raise ValueError("SQLite database identity changed during connect")
        return connection
    finally:
        os.close(descriptor)


def connect_trusted_sqlite_read_only(database_path: Path) -> sqlite3.Connection:
    """Open an existing private database without creating or repairing files."""
    parent = database_path.parent
    parent_metadata = os.lstat(parent)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent.is_symlink()
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o077
    ):
        raise ValueError("SQLite parent must be an existing trusted private directory")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(database_path, flags)
    try:
        metadata = _validate_private_sqlite_descriptor(descriptor)
        sidecar_descriptors: list[int] = []
        sidecar_metadata: dict[Path, os.stat_result] = {}
        sidecars = (Path(f"{database_path}-wal"), Path(f"{database_path}-shm"))
        sidecar_presence = tuple(sidecar.exists() for sidecar in sidecars)
        if any(sidecar_presence) and not all(sidecar_presence):
            raise ValueError("SQLite WAL read requires existing trusted WAL and SHM sidecars")
        try:
            for sidecar in sidecars if all(sidecar_presence) else ():
                sidecar_descriptor = os.open(sidecar, flags)
                sidecar_descriptors.append(sidecar_descriptor)
                sidecar_metadata[sidecar] = _validate_private_sqlite_descriptor(sidecar_descriptor)
            query = "mode=ro" if sidecar_metadata else "mode=ro&immutable=1"
            absolute_path = database_path.absolute()
            uri = f"file:{quote(str(absolute_path), safe='/')}?{query}"
            connection = sqlite3.connect(uri, uri=True)
        finally:
            for sidecar_descriptor in reversed(sidecar_descriptors):
                os.close(sidecar_descriptor)
        current = os.lstat(database_path)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            connection.close()
            raise ValueError("SQLite database identity changed during read-only connect")
        for sidecar, expected in sidecar_metadata.items():
            current_sidecar = os.lstat(sidecar)
            if (current_sidecar.st_dev, current_sidecar.st_ino) != (expected.st_dev, expected.st_ino):
                connection.close()
                raise ValueError("SQLite sidecar identity changed during read-only connect")
        return connection
    finally:
        os.close(descriptor)


def _validate_private_sqlite_descriptor(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("SQLite data must be an existing trusted private file")
    return metadata


def secure_sqlite_files(database_path: Path) -> None:
    for candidate in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        try:
            metadata = os.lstat(candidate)
        except FileNotFoundError:
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or candidate.is_symlink()
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ValueError("SQLite data files must be trusted regular files")
        candidate.chmod(0o600)


@contextmanager
def sqlite_read_lock(database_path: Path) -> Iterator[None]:
    """Share the existing application lock without creating or repairing it."""
    lock_path = database_path.parent / f"{database_path.name}.write.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        _validate_private_sqlite_descriptor(descriptor)
        if fcntl is None:  # pragma: no cover - non-POSIX fallback
            yield
            return
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


@contextmanager
def sqlite_write_lock(database_path: Path) -> Iterator[None]:
    lock_path = database_path.parent / f"{database_path.name}.write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    parent = os.lstat(lock_path.parent)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or lock_path.parent.is_symlink()
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        raise ValueError("SQLite lock parent must be a trusted private directory")
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise ValueError("SQLite lock must be a trusted regular file")
        os.fchmod(descriptor, 0o600)
        if fcntl is None:  # pragma: no cover - non-POSIX fallback
            yield
            return
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
