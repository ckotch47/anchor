from __future__ import annotations

from typing import Protocol


class HealthPort(Protocol):
    def health(self): ...


class MaintenancePort(Protocol):
    def checkpoint_wal(self) -> dict[str, int]: ...

    def auto_maintain_if_due(self, *, interval_days: int = 7) -> bool: ...
