from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.adapters.sqlite_events_repository import SqliteProviderEgressAuditRepository
from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_health_repository import SqliteHealthRepository
from anchor.adapters.sqlite_history_repository import SqliteHistoryRepository
from anchor.adapters.sqlite_links_repository import SqliteLinksRepository
from anchor.adapters.sqlite_maintenance_repository import SqliteMaintenanceRepository
from anchor.adapters.sqlite_memory_repository import SqliteMemoryRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.adapters.sqlite_notes_repository import SqliteNotesRepository
from anchor.adapters.sqlite_projects_repository import SqliteProjectsRepository
from anchor.adapters.sqlite_tasks_repository import SqliteTasksRepository
from anchor.application.embeddings.provider_service import OpenAICompatibleEmbeddingsProvider
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.service import FilesService
from anchor.application.history.service import HistoryService
from anchor.application.links.service import DocumentLinksService
from anchor.application.memory.provider_service import OpenAICompatibleMemoryExtractionProvider
from anchor.application.memory.service import MemoryService
from anchor.application.notes.service import NotesService
from anchor.application.provider_security import ProviderEgressPolicy
from anchor.application.retrieval.document_chunking import DocumentChunkingService
from anchor.application.retrieval.rerank_provider_service import NativeRerankProvider, OpenAICompatibleRerankProvider
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_service import SearchService
from anchor.application.system.config_service import ConfigService
from anchor.application.system.health_service import HealthService
from anchor.application.system.maintenance_service import MaintenanceService
from anchor.application.system.metadata_service import MetadataSchemaService
from anchor.application.system.migration_service import MigrationService
from anchor.application.system.projects_service import ProjectsService
from anchor.application.tasks.service import TasksService
from anchor.config import AppConfig, default_data_dir, default_database_path, ensure_private_default_data_dir


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
    links_service: DocumentLinksService
    memory_service: MemoryService
    projects_service: ProjectsService


def build_container(profile: str | None = None, auto_migrate: bool = True) -> Container:
    database_path = default_database_path()
    if auto_migrate and database_path.parent == default_data_dir():
        ensure_private_default_data_dir()
    repo = FileSystemConfigRepository()
    config, config_path, profile_name = repo.load(profile=profile)
    config_service = ConfigService(repository=repo)
    provider_audit = SqliteProviderEgressAuditRepository(database_path=database_path)
    maintenance_service = MaintenanceService(repository=SqliteMaintenanceRepository(database_path=database_path))
    migration_service = MigrationService(repository=SqliteMigrationRepository(database_path=database_path))
    health_service = HealthService(
        config=config,
        snapshot_port=SqliteHealthRepository(database_path=database_path),
    )
    links_service = DocumentLinksService(
        repository=SqliteLinksRepository(database_path=database_path),
        config=config.links,
    )
    embedding_service = None
    rerank_service = None
    if not config.runtime.offline_only:
        embedding_model = config.provider.embedding_model.strip()
        rerank_model = config.provider.rerank_model.strip()
        if embedding_model:
            embeddings_provider = OpenAICompatibleEmbeddingsProvider(
                base_url=config.provider.base_url,
                api_key_env=config.provider.api_key_env,
            )
            embedding_service = EmbeddingService(
                provider=embeddings_provider,
                model=embedding_model,
                max_batch_items=config.provider.max_batch_items,
                max_batch_characters=config.provider.max_batch_characters,
                egress_policy=ProviderEgressPolicy(
                    endpoint=embeddings_provider.endpoint,
                    external_send_allowed=config.runtime.embedding_external_send,
                    external_projects=tuple(config.runtime.embedding_external_projects),
                ),
                audit_port=provider_audit,
            )
        if rerank_model:
            rerank_provider = (
                NativeRerankProvider(
                    base_url=config.provider.rerank_base_url,
                    api_key_env=config.provider.rerank_api_key_env,
                    max_response_bytes=config.provider.rerank_max_response_bytes,
                )
                if config.provider.rerank_base_url.strip()
                else OpenAICompatibleRerankProvider(
                    base_url=config.provider.base_url,
                    api_key_env=config.provider.api_key_env,
                    max_response_bytes=config.provider.rerank_max_response_bytes,
                )
            )
            rerank_service = RerankService(
                provider=rerank_provider,
                model=rerank_model,
                max_batch_items=config.provider.max_batch_items,
                max_batch_characters=config.provider.max_batch_characters,
                egress_policy=ProviderEgressPolicy(
                    endpoint=rerank_provider.endpoint,
                    external_send_allowed=config.runtime.rerank_external_send,
                    external_projects=tuple(config.runtime.rerank_external_projects),
                ),
                audit_port=provider_audit,
            )
    metadata_service = MetadataSchemaService(config.metadata)
    notes_service = NotesService(
        repository=SqliteNotesRepository(database_path=database_path, vector_dimension=config.vector.dimension),
        chunking_service=DocumentChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        metadata_service=metadata_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    history_service = HistoryService(
        repository=SqliteHistoryRepository(database_path=database_path, vector_dimension=config.vector.dimension),
        chunking_service=DocumentChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        metadata_service=metadata_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    tasks_service = TasksService(
        repository=SqliteTasksRepository(database_path=database_path),
        project=config.runtime.default_project,
        metadata_service=metadata_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    files_service = FilesService(
        repository=SqliteFilesRepository(database_path=database_path, vector_dimension=config.vector.dimension),
        chunking_service=FileChunkingService(),
        project=config.runtime.default_project,
        embedding_service=embedding_service,
        rerank_service=rerank_service,
        metadata_service=metadata_service,
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
        embedding_service=embedding_service,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    projects_service = ProjectsService(
        repository=SqliteProjectsRepository(database_path=database_path),
    )
    memory_service = MemoryService(
        repository=SqliteMemoryRepository(database_path=database_path),
        project=config.runtime.default_project,
        budget_tokens=config.runtime.default_budget_tokens,
    )
    if not config.runtime.offline_only and config.provider.memory_model.strip():
        memory_service.configure_extraction(
            OpenAICompatibleMemoryExtractionProvider(
                base_url=config.provider.base_url,
                api_key_env=config.provider.api_key_env,
            ),
            model=config.provider.memory_model,
            external_send_allowed=config.runtime.memory_external_send,
            external_projects=config.runtime.memory_external_projects,
            provider_name=config.provider.base_url,
            max_extracted_facts=config.runtime.memory_extract_max_facts,
        )
    history_service.configure_memory_extraction(
        memory_service.extract,
        enabled=config.runtime.memory_auto_extract and config.runtime.memory_external_send,
        batch_size=config.runtime.memory_extract_batch_size,
        min_interval_seconds=config.runtime.memory_extract_min_interval_seconds,
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
        links_service=links_service,
        memory_service=memory_service,
        projects_service=projects_service,
    )
