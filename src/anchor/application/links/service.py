from __future__ import annotations

from anchor.adapters.sqlite_links_repository import SqliteLinksRepository
from anchor.application.links.models import DocumentLinkListResult, DocumentLinkRecord
from anchor.config import LinksConfig


class DocumentLinksService:
    def __init__(self, repository: SqliteLinksRepository, config: LinksConfig | None = None) -> None:
        self._repository = repository
        self._config = config or LinksConfig()

    def create(self, source_id: str, target_id: str, relation_type: str) -> DocumentLinkRecord:
        self._require_non_empty(source_id, "source_id")
        self._require_non_empty(target_id, "target_id")
        self._require_non_empty(relation_type, "relation_type")
        self._validate_relation_type(relation_type)
        return self._repository.create(source_id=source_id, target_id=target_id, relation_type=relation_type)

    def list_by_source(self, source_id: str) -> DocumentLinkListResult:
        self._require_non_empty(source_id, "source_id")
        links = self._repository.list_by_source(source_id)
        return DocumentLinkListResult(count=len(links), links=links)

    def list_by_target(self, target_id: str) -> DocumentLinkListResult:
        self._require_non_empty(target_id, "target_id")
        links = self._repository.list_by_target(target_id)
        return DocumentLinkListResult(count=len(links), links=links)

    def delete(self, source_id: str, target_id: str, relation_type: str) -> bool:
        self._require_non_empty(source_id, "source_id")
        self._require_non_empty(target_id, "target_id")
        self._require_non_empty(relation_type, "relation_type")
        self._validate_relation_type(relation_type)
        return self._repository.delete(source_id=source_id, target_id=target_id, relation_type=relation_type)

    def _validate_relation_type(self, relation_type: str) -> None:
        if self._config.relation_types and relation_type not in self._config.relation_types:
            raise ValueError(f"unsupported relation_type: {relation_type}")

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")
