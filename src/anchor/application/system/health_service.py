from __future__ import annotations

from pydantic import BaseModel

from anchor.application.system.ports import MaintenancePort
from anchor.config import AppConfig


class HealthResult(BaseModel):
    status: str = "ok"
    storage: str = "sqlite"
    mode: str = "offline-only"


class HealthService:
    def __init__(self, config: AppConfig, maintenance_port: MaintenancePort | None = None) -> None:
        self._config = config
        self._maintenance_port = maintenance_port

    def health(self) -> HealthResult:
        if self._maintenance_port is not None:
            try:
                self._maintenance_port.auto_maintain_if_due()
            except Exception:
                pass
        mode = "offline-only" if self._config.runtime.offline_only else "online-enabled"
        return HealthResult(mode=mode)
