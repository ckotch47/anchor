from __future__ import annotations

from pydantic import BaseModel, Field

from anchor.application.system.ports import HealthSnapshotPort
from anchor.config import AppConfig


class HealthResult(BaseModel):
    status: str = "ok"
    ready: bool = True
    storage: str = "sqlite"
    mode: str = "offline-only"
    checks: dict[str, str] = Field(default_factory=dict)
    index_error_count: int = 0
    pending_migrations: list[int] = Field(default_factory=list)
    unexpected_migrations: list[int] = Field(default_factory=list)


class HealthService:
    def __init__(self, config: AppConfig, snapshot_port: HealthSnapshotPort) -> None:
        self._config = config
        self._snapshot_port = snapshot_port

    def health(self) -> HealthResult:
        mode = "offline-only" if self._config.runtime.offline_only else "online-enabled"
        snapshot = self._snapshot_port.snapshot()
        return HealthResult.model_validate({"mode": mode, **snapshot})
