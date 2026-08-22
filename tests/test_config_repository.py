from __future__ import annotations

import sqlite3
import stat
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.system.config_service import ConfigService


class ConfigRepositoryTest(unittest.TestCase):
    def test_default_config_is_used_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = FileSystemConfigRepository(config_path=Path(tmpdir) / "config.toml")
            config, config_path, profile = repo.load()

        self.assertEqual(config.runtime.default_view, "compact")
        self.assertEqual(config.runtime.default_limit, 20)
        self.assertEqual(config.runtime.default_project, "workspace")
        self.assertEqual(str(config_path), str(Path(tmpdir) / "config.toml"))
        self.assertIsNone(profile)

    def test_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)
            service = ConfigService(repository=repo)

            service.set(section="runtime", key="default_view", value="full")
            result = service.get()
            mode = stat.S_IMODE(config_path.stat().st_mode)

        self.assertEqual(result.config.runtime.default_view, "full")
        self.assertEqual(result.config_path, str(config_path))
        self.assertEqual(mode, 0o600)

    def test_config_load_rejects_symlink_and_insecure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            external = root / "external.toml"
            external.write_text("[runtime]\ndefault_project = \"attacker\"\n", encoding="utf-8")
            external.chmod(0o600)
            symlink = root / "symlink.toml"
            symlink.symlink_to(external)

            with self.assertRaises((OSError, ValueError)):
                FileSystemConfigRepository(config_path=symlink).load_raw()

            insecure = root / "insecure.toml"
            insecure.write_text("[runtime]\ndefault_project = \"attacker\"\n", encoding="utf-8")
            insecure.chmod(0o644)
            with self.assertRaises(ValueError):
                FileSystemConfigRepository(config_path=insecure).load_raw()
            self.assertEqual(stat.S_IMODE(insecure.stat().st_mode), 0o644)

    def test_init_from_example_creates_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)

            config, created_path = repo.init_from_example()

            self.assertTrue(config_path.exists())
            self.assertEqual(created_path, config_path)
            self.assertEqual(config.runtime.default_project, "workspace")

    def test_init_from_example_uses_packaged_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)

            config, created_path = repo.init_from_example(force=True)
            self.assertTrue(config_path.exists())
            self.assertEqual(created_path, config_path)
            self.assertEqual(config.runtime.default_view, "compact")

    def test_init_from_example_rejects_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = FileSystemConfigRepository(config_path=config_path)
            repo.save(repo.load_raw()[0])

            with self.assertRaises(FileExistsError):
                repo.init_from_example()

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

            with closing(sqlite3.connect(db_path)) as connection:
                tables = {
                    row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                version_rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
                fts_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(document_chunks_fts)").fetchall()
                }
                task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()}
                document_columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}

            self.assertEqual(result.applied, 13)
        self.assertEqual(result.current_version, 13)
        self.assertIn("schema_migrations", tables)
        self.assertIn("documents", tables)
        self.assertIn("notes", tables)
        self.assertIn("tasks", tables)
        self.assertIn("history_entries", tables)
        self.assertIn("document_chunks", tables)
        self.assertIn("chunk_embeddings", tables)
        self.assertIn("document_chunks_fts", tables)
        self.assertIn("indexed_files", tables)
        self.assertIn("file_chunks", tables)
        self.assertIn("file_chunks_fts", tables)
        self.assertIn("document_tags", tables)
        self.assertIn("document_links", tables)
        self.assertIn("events", tables)
        self.assertIn("settings", tables)
        self.assertIn("index_states", tables)
        self.assertIn("memory_facts", tables)
        self.assertIn("memory_facts_fts", tables)
        self.assertIn("memory_pipeline_checkpoints", tables)
        self.assertIn("memory_scenarios", tables)
        self.assertIn("memory_scenarios_fts", tables)
        self.assertNotIn("items", tables)
        self.assertIn("document_type", fts_columns)
        self.assertIn("task_kind", task_columns)
        self.assertIn("started_at", task_columns)
        self.assertIn("parent_document_id", task_columns)
        self.assertIn("blocked_by_document_id", task_columns)
        self.assertIn("external_key", task_columns)
        self.assertIn("correlation_id", document_columns)
        self.assertEqual(version_rows, [(version,) for version in range(1, 14)])
