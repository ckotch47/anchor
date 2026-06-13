from __future__ import annotations

from pydantic import BaseModel

from anchor.config import AppConfig


class HealthResult(BaseModel):
    status: str = "ok"
    storage: str = "sqlite"
    mode: str = "offline-only"


class HealthService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def health(self) -> HealthResult:
        mode = "offline-only" if self._config.runtime.offline_only else "online-enabled"
        return HealthResult(mode=mode)
