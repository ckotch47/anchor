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
