from __future__ import annotations

from dataclasses import dataclass

from anchor.adapters.sqlite_projects_repository import SqliteProjectsRepository


@dataclass(frozen=True)
class ProjectsListResult:
    projects: list[str]
    count: int


class ProjectsService:
    def __init__(self, repository: SqliteProjectsRepository) -> None:
        self._repository = repository

    def list_projects(self) -> ProjectsListResult:
        projects = self._repository.list_projects()
        return ProjectsListResult(projects=projects, count=len(projects))
