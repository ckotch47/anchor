from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_history_repository import SqliteHistoryRepository
from anchor.adapters.sqlite_maintenance_repository import SqliteMaintenanceRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.embeddings.provider_service import OpenAICompatibleEmbeddingsProvider
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.service import FilesService
from anchor.application.history.service import HistoryService
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_service import SearchService
from anchor.application.system.config_service import ConfigService
from anchor.application.system.health_service import HealthService
from anchor.application.system.maintenance_service import MaintenanceService
from anchor.application.system.migration_service import MigrationService
from anchor.application.tasks.service import TasksService
from anchor.config import AppConfig, default_database_path


@dataclass(frozen=True)
class Container:
    config: AppConfig
    config_path: str
    profile_name: str | None
    health_service: HealthService
    maintenance_service: MaintenanceService
    config_service: ConfigService
    migration_service: MigrationService
    notes_service: NotesService
    history_service: HistoryService
    tasks_service: TasksService
    files_service: FilesService
    search_service: SearchService


def build_container(profile: str | None = None, auto_migrate: bool = True) -> Container:
    repo = FileSystemConfigRepository()
    config, config_path, profile_name = repo.load(profile=profile)
    config_service = ConfigService(repository=repo)
    database_path = default_database_path()
    maintenance_service = MaintenanceService(repository=SqliteMaintenanceRepository(database_path=database_path))
    migration_service = MigrationService(repository=SqliteMigrationRepository(database_path=database_path))
    health_service = HealthService(config=config, maintenance_port=maintenance_service)
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
        repository=SqliteNotesRepository(database_path=database_path, vector_dimension=config.vector.dimension),
        chunking_service=DocumentChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    history_service = HistoryService(
        repository=SqliteHistoryRepository(database_path=database_path, vector_dimension=config.vector.dimension),
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
    files_service = FilesService(
        repository=SqliteFilesRepository(database_path=database_path, vector_dimension=config.vector.dimension),
        chunking_service=FileChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        roots=config.filesystem.roots,
        ignore_patterns=config.filesystem.ignore_patterns,
        max_file_size=config.filesystem.max_file_size,
        chunk_size=config.vector.chunk_size,
        chunk_overlap=config.vector.chunk_overlap,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    search_service = SearchService(
        notes_service=notes_service,
        history_service=history_service,
        tasks_service=tasks_service,
        files_service=files_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    if auto_migrate:
        migration_service.migrate()
    return Container(
        config=config,
        config_path=str(config_path),
        profile_name=profile_name,
        health_service=health_service,
        maintenance_service=maintenance_service,
        config_service=config_service,
        migration_service=migration_service,
        notes_service=notes_service,
        history_service=history_service,
        tasks_service=tasks_service,
        files_service=files_service,
        search_service=search_service,
    )
