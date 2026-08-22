from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from anchor.config import AppConfig
from anchor.container import build_container


class ContainerTest(unittest.TestCase):
    def test_default_data_directory_is_secured_before_config_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.toml"
            events: list[str] = []
            repo = Mock()

            def load(*, profile=None):
                del profile
                events.append("load")
                return AppConfig.default(), config_path, None

            repo.load.side_effect = load
            with patch("anchor.container.default_data_dir", return_value=root):
                with patch("anchor.container.default_database_path", return_value=root / "anchor.sqlite3"):
                    with patch("anchor.container.ensure_private_default_data_dir", side_effect=lambda: events.append("secure")):
                        with patch("anchor.container.FileSystemConfigRepository", return_value=repo):
                            with patch("anchor.container.MigrationService"):
                                build_container()

        self.assertEqual(events[:2], ["secure", "load"])

    def test_build_container_auto_migrates_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            repo = Mock()
            repo.load.return_value = (AppConfig.default(), config_path, None)
            migration_service = Mock()

            with patch("anchor.container.FileSystemConfigRepository", return_value=repo):
                with patch("anchor.container.SqliteMigrationRepository"):
                    with patch("anchor.container.MigrationService", return_value=migration_service):
                        container = build_container()

        migration_service.migrate.assert_called_once()
        self.assertEqual(container.config_path, str(config_path))

    def test_build_container_skips_optional_providers_when_models_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = AppConfig.default()
            config.runtime.offline_only = False
            config.provider.embedding_model = ""
            config.provider.rerank_model = ""
            repo = Mock()
            repo.load.return_value = (config, config_path, None)
            migration_service = Mock()

            with patch("anchor.container.FileSystemConfigRepository", return_value=repo):
                with patch("anchor.container.SqliteMigrationRepository"):
                    with patch("anchor.container.MigrationService", return_value=migration_service):
                        with patch("anchor.container.OpenAICompatibleEmbeddingsProvider") as embeddings_provider:
                            with patch("anchor.container.OpenAICompatibleRerankProvider") as rerank_provider:
                                container = build_container()

        migration_service.migrate.assert_called_once()
        embeddings_provider.assert_not_called()
        rerank_provider.assert_not_called()
        self.assertIsNone(container.search_service._embedding_service)

    def test_build_container_uses_native_rerank_endpoint_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = AppConfig.default()
            config.runtime.offline_only = False
            config.provider.embedding_model = ""
            config.provider.rerank_model = "reranker"
            config.provider.rerank_base_url = "http://127.0.0.1:8080"
            repo = Mock()
            repo.load.return_value = (config, config_path, None)
            migration_service = Mock()

            with patch("anchor.container.FileSystemConfigRepository", return_value=repo):
                with patch("anchor.container.SqliteMigrationRepository"):
                    with patch("anchor.container.MigrationService", return_value=migration_service):
                        with patch("anchor.container.NativeRerankProvider") as native_provider:
                            with patch("anchor.container.OpenAICompatibleRerankProvider") as chat_provider:
                                build_container()

        native_provider.assert_called_once_with(
            base_url="http://127.0.0.1:8080",
            api_key_env="",
            max_response_bytes=1_048_576,
        )
        chat_provider.assert_not_called()
