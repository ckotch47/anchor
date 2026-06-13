from __future__ import annotations

from typing import Protocol

from anchor.application.system.health_service import HealthResult


class HealthPort(Protocol):
    def health(self) -> HealthResult: ...
