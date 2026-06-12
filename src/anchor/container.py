from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.config_service import ConfigService
from anchor.application.health_service import HealthService
from anchor.application.migration_service import MigrationService
from anchor.config import AppConfig


@dataclass(frozen=True)
class Container:
    config: AppConfig
    config_path: str
    profile_name: str | None
    health_service: HealthService
    config_service: ConfigService
    migration_service: MigrationService


def build_container(profile: str | None = None, auto_migrate: bool = True) -> Container:
    repo = FileSystemConfigRepository()
    config, config_path, profile_name = repo.load(profile=profile)
    health_service = HealthService(config=config)
    config_service = ConfigService(repository=repo)
    migration_service = MigrationService(repository=SqliteMigrationRepository())
    if auto_migrate:
        migration_service.migrate()
    return Container(
        config=config,
        config_path=str(config_path),
        profile_name=profile_name,
        health_service=health_service,
        config_service=config_service,
        migration_service=migration_service,
    )
