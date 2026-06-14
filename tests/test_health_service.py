from __future__ import annotations

import unittest
from unittest.mock import Mock

from anchor.application.system.health_service import HealthService
from anchor.config import AppConfig


class HealthServiceTest(unittest.TestCase):
    def test_health_triggers_best_effort_maintenance(self) -> None:
        maintenance_port = Mock()
        service = HealthService(config=AppConfig.default(), maintenance_port=maintenance_port)

        result = service.health()

        maintenance_port.auto_maintain_if_due.assert_called_once()
        self.assertEqual(result.mode, "offline-only")
