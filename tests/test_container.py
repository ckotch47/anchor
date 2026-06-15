from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from anchor.config import AppConfig
from anchor.container import build_container


class ContainerTest(unittest.TestCase):
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
