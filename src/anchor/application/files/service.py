from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.models import FileSearchHit, FilesIndexResult, FilesSearchResult
from anchor.application.retrieval.document_chunking import count_tokens

_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
}

_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "text",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class FilesService:
    def __init__(
        self,
        repository: SqliteFilesRepository,
        chunking_service: FileChunkingService,
        project: str,
        roots: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        max_file_size: int = 1_000_000,
        chunk_size: int = 400,
        chunk_overlap: int = 50,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._chunking_service = chunking_service
        self._project = project
        self._roots = roots or []
        self._ignore_patterns = ignore_patterns or []
        self._max_file_size = max_file_size
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._budget_tokens = budget_tokens

    def index(self, roots: list[str] | None = None, *, project: str | None = None) -> FilesIndexResult:
        resolved_project = project or self._project
        resolved_roots = [Path(root).expanduser().resolve() for root in (roots or self._roots or [Path.cwd()])]
        indexed = 0
        skipped = 0
        deleted = 0
        seen_paths: set[str] = set()
        for root in resolved_roots:
            if not root.exists() or not root.is_dir():
                continue
            gitignore_cache: dict[Path, list[str]] = {}
            for file_path in self._walk_files(root):
                if self._should_ignore(file_path, root, gitignore_cache):
                    skipped += 1
                    continue
                if not file_path.is_file():
                    continue
                stat = file_path.stat()
                if stat.st_size > self._max_file_size:
                    skipped += 1
                    continue
                if self._is_binary(file_path):
                    skipped += 1
                    continue
                try:
                    raw_text = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                relative_path = file_path.as_posix()
                seen_paths.add(relative_path)
                content_hash = self._hash_text(raw_text)
                existing = self._repository.get_by_path(project=resolved_project, path=relative_path)
                if (
                    existing is not None
                    and existing.content_hash == content_hash
                    and existing.file_size == stat.st_size
                    and existing.mtime_ns == stat.st_mtime_ns
                ):
                    continue
                language = self._detect_language(file_path)
                chunks = self._chunking_service.chunk_file(
                    path=file_path,
                    text=raw_text,
                    language=language,
                    chunk_size=self._chunk_size,
                    chunk_overlap=self._chunk_overlap,
                )
                document_id = self._document_id(resolved_project, relative_path)
                self._repository.upsert_file(
                    document_id=document_id,
                    project=resolved_project,
                    path=relative_path,
                    root_path=root.as_posix(),
                    language=language,
                    metatags={},
                    file_size=stat.st_size,
                    content_hash=content_hash,
                    mtime_ns=stat.st_mtime_ns,
                    chunks=chunks,
                )
                indexed += 1
        for record in self._repository.list_indexed_files(project=resolved_project):
            if record.path not in seen_paths and self._root_matches(record.root_path, resolved_roots):
                self._repository.delete(record.id, project=resolved_project)
                deleted += 1
        return FilesIndexResult(count=indexed + deleted, indexed=indexed, skipped=skipped, deleted=deleted)

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
    ) -> FilesSearchResult:
        self._require_non_empty(query, "query")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        resolved_project = project or self._project
        results = self._trim_to_budget(
            self._repository.search(query=query, limit=limit, project=resolved_project),
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        return FilesSearchResult(query=query, count=len(results), results=results)

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

    @staticmethod
    def _document_id(project: str, path: str) -> str:
        digest = hashlib.sha256(f"{project}:{path}".encode()).hexdigest()
        return f"file_{digest}"

    def _walk_files(self, root: Path):
        for current in root.rglob("*"):
            if current.is_dir():
                continue
            yield current

    def _should_ignore(self, path: Path, root: Path, gitignore_cache: dict[Path, list[str]]) -> bool:
        relative_path = path.relative_to(root).as_posix()
        candidate_dirs = [root, *path.parents]
        patterns = list(self._ignore_patterns)
        for directory in candidate_dirs:
            if directory == root.parent:
                break
            if directory.is_dir() and directory not in gitignore_cache:
                gitignore_path = directory / ".gitignore"
                if gitignore_path.exists():
                    gitignore_cache[directory] = [
                        line.strip()
                        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                    ]
                else:
                    gitignore_cache[directory] = []
            patterns.extend(gitignore_cache.get(directory, []))
        return any(self._pattern_matches(pattern, relative_path, path.name) for pattern in patterns)

    @staticmethod
    def _pattern_matches(pattern: str, relative_path: str, filename: str) -> bool:
        normalized = pattern.strip()
        if not normalized:
            return False
        if normalized.endswith("/"):
            return relative_path.startswith(normalized.rstrip("/"))
        if "/" in normalized:
            return fnmatch.fnmatch(relative_path, normalized)
        return fnmatch.fnmatch(filename, normalized) or fnmatch.fnmatch(relative_path, normalized)

    @staticmethod
    def _is_binary(path: Path) -> bool:
        if path.suffix.lower() in _BINARY_SUFFIXES:
            return True
        try:
            with path.open("rb") as handle:
                sample = handle.read(512)
        except OSError:
            return True
        if b"\x00" in sample:
            return True
        return False

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _detect_language(path: Path) -> str:
        return _LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")

    @staticmethod
    def _root_matches(root_path: str, roots: list[Path]) -> bool:
        resolved_root = Path(root_path).resolve()
        return any(resolved_root == root.resolve() for root in roots)

    def _trim_to_budget(self, results: list[FileSearchHit], budget_tokens: int) -> list[FileSearchHit]:
        if budget_tokens <= 0:
            return []
        trimmed: list[FileSearchHit] = []
        total_tokens = 0
        for result in results:
            result_cost = self._estimate_result_tokens(result)
            if trimmed and total_tokens + result_cost > budget_tokens:
                break
            trimmed.append(result)
            total_tokens += result_cost
        return trimmed

    @staticmethod
    def _estimate_result_tokens(result: FileSearchHit) -> int:
        return max(1, count_tokens(result.file.path) + count_tokens(result.snippet))
