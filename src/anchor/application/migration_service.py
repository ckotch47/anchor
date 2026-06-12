from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.sqlite_migration_repository import MigrationApplicationResult, SqliteMigrationRepository


@dataclass(frozen=True)
class MigrationResult:
    database_path: str
    applied: int
    current_version: int
    applied_versions: list[int]


class MigrationService:
    def __init__(self, repository: SqliteMigrationRepository) -> None:
        self._repository = repository

    def migrate(self) -> MigrationResult:
        result: MigrationApplicationResult = self._repository.apply_pending()
        return MigrationResult(
            database_path=str(result.database_path),
            applied=result.applied,
            current_version=result.current_version,
            applied_versions=list(result.applied_versions),
        )

