from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.embeddings.provider_service import OpenAICompatibleEmbeddingsProvider
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.system.config_service import ConfigService
from anchor.application.system.health_service import HealthService
from anchor.application.system.migration_service import MigrationService
from anchor.application.tasks.service import TasksService
from anchor.config import AppConfig, default_database_path


@dataclass(frozen=True)
class Container:
    config: AppConfig
    config_path: str
    profile_name: str | None
    health_service: HealthService
    config_service: ConfigService
    migration_service: MigrationService
    notes_service: NotesService
    tasks_service: TasksService


def build_container(profile: str | None = None, auto_migrate: bool = True) -> Container:
    repo = FileSystemConfigRepository()
    config, config_path, profile_name = repo.load(profile=profile)
    health_service = HealthService(config=config)
    config_service = ConfigService(repository=repo)
    database_path = default_database_path()
    migration_service = MigrationService(repository=SqliteMigrationRepository(database_path=database_path))
    embedding_service = None
    rerank_service = None
    if not config.runtime.offline_only:
        embeddings_provider = OpenAICompatibleEmbeddingsProvider(
            base_url=config.provider.base_url,
            api_key_env=config.provider.api_key_env,
        )
        embedding_service = EmbeddingService(
            provider=embeddings_provider,
            model=config.provider.embedding_model,
        )
        rerank_service = RerankService(
            embedding_service=EmbeddingService(
                provider=embeddings_provider,
                model=config.provider.rerank_model,
            )
        )
    notes_service = NotesService(
        repository=SqliteNotesRepository(database_path=database_path),
        chunking_service=DocumentChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    tasks_service = TasksService(
        repository=SqliteTasksRepository(database_path=database_path),
        project=config.runtime.default_project,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    if auto_migrate:
        migration_service.migrate()
    return Container(
        config=config,
        config_path=str(config_path),
        profile_name=profile_name,
        health_service=health_service,
        config_service=config_service,
        migration_service=migration_service,
        notes_service=notes_service,
        tasks_service=tasks_service,
    )
