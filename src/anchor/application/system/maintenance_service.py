from __future__ import annotations

from pydantic import BaseModel, Field

from anchor.adapters.sqlite_maintenance_repository import SqliteMaintenanceRepository


class MaintenanceResult(BaseModel):
    purged_documents: int = 0
    rebuilt_indexes: list[str] = Field(default_factory=list)
    vacuumed: bool = False
    checkpoint: dict[str, int] | None = None


class MaintenanceService:
    def __init__(self, repository: SqliteMaintenanceRepository) -> None:
        self._repository = repository

    def checkpoint_wal(self) -> dict[str, int]:
        return self._repository.checkpoint_wal()

    def auto_maintain_if_due(self, *, interval_days: int = 7) -> bool:
        return self._repository.auto_maintain_if_due(interval_days=interval_days)

    def compact(
        self,
        *,
        project: str | None = None,
        deleted_before: str | None = None,
        rebuild_indexes: bool = True,
        vacuum: bool = True,
        checkpoint: bool = True,
    ) -> MaintenanceResult:
        purged_documents = self._repository.purge_deleted_documents(project=project, deleted_before=deleted_before)
        rebuilt_indexes = self._repository.rebuild_search_indexes() if rebuild_indexes else []
        vacuumed = False
        if vacuum:
            self._repository.vacuum()
            vacuumed = True
        checkpoint_result = self._repository.checkpoint_wal() if checkpoint else None
        return MaintenanceResult(
            purged_documents=purged_documents,
            rebuilt_indexes=rebuilt_indexes,
            vacuumed=vacuumed,
            checkpoint=checkpoint_result,
        )
