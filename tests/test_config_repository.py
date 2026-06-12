from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.application.config_service import ConfigService
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository


class ConfigRepositoryTest(unittest.TestCase):
    def test_default_config_is_used_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = FileSystemConfigRepository(config_path=Path(tmpdir) / "config.toml")
            config, config_path, profile = repo.load()

        self.assertEqual(config.runtime.default_view, "compact")
        self.assertEqual(config.runtime.default_limit, 20)
        self.assertEqual(str(config_path), str(Path(tmpdir) / "config.toml"))
        self.assertIsNone(profile)

    def test_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)
            service = ConfigService(repository=repo)

            service.set(section="runtime", key="default_view", value="full")
            result = service.get()

        self.assertEqual(result.config.runtime.default_view, "full")
        self.assertEqual(result.config_path, str(config_path))

    def test_profile_overlay_does_not_mutate_raw_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)
            repo.save(repo.load_raw()[0])

            effective_config, _, _ = repo.load(profile="full")
            raw_config, _ = repo.load_raw()

        self.assertEqual(effective_config.runtime.default_view, "full")
        self.assertEqual(raw_config.runtime.default_view, "compact")

    def test_migration_repository_applies_initial_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            repo = SqliteMigrationRepository(database_path=db_path)
            result = repo.apply_pending()

            with sqlite3.connect(db_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                version_rows = connection.execute("SELECT version FROM schema_migrations").fetchall()

        self.assertEqual(result.applied, 1)
        self.assertEqual(result.current_version, 1)
        self.assertIn("schema_migrations", tables)
        self.assertIn("items", tables)
        self.assertEqual(version_rows, [(1,)])
