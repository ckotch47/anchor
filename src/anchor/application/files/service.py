from __future__ import annotations

import base64
import builtins
import fnmatch
import hashlib
import json
import os
import stat as stat_module
from collections import OrderedDict
from pathlib import Path
from time import monotonic

from anchor.adapters.sqlite_files_repository import SqliteFilesRepository
from anchor.adapters.sqlite_ids import uuid7_str
from anchor.application.embeddings.service import EmbeddingService
from anchor.application.files.chunking import FileChunkingService
from anchor.application.files.models import (
    FileIndexDraft,
    FileListItem,
    FileSearchCandidate,
    FileSearchHit,
    FilesGetResult,
    FilesIndexResult,
    FilesListResult,
    FilesSearchResult,
    IndexedFileRecord,
)
from anchor.application.provider_security import safe_provider_error
from anchor.application.retrieval.compact_items import compact_file_item
from anchor.application.retrieval.document_chunking import count_tokens
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_query import MAX_RETRIEVAL_LIMIT, validate_retrieval_limit
from anchor.application.retrieval.search_scoring import combine_search_scores
from anchor.application.system.metadata_service import MetadataSchemaService

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
        embedding_service: EmbeddingService | None = None,
        rerank_service: RerankService | None = None,
        metadata_service: MetadataSchemaService | None = None,
        roots: builtins.list[str] | None = None,
        ignore_patterns: builtins.list[str] | None = None,
        max_file_size: int = 1_000_000,
        chunk_size: int = 400,
        chunk_overlap: int = 50,
        budget_tokens: int = 800,
    ) -> None:
        self._repository = repository
        self._chunking_service = chunking_service
        self._project = project
        self._embedding_service = embedding_service
        self._rerank_service = rerank_service
        self._metadata_service = metadata_service
        self._roots = roots or []
        self._ignore_patterns = ignore_patterns or []
        self._max_file_size = max_file_size
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._budget_tokens = budget_tokens

    def index(
        self,
        roots: builtins.list[str] | None = None,
        *,
        project: str | None = None,
        force: bool = False,
    ) -> FilesIndexResult:
        resolved_project = project or self._project
        resolved_roots = self._resolve_roots(roots, resolved_project)
        indexed = 0
        skipped = 0
        deleted = 0
        seen_paths: set[str] = set()
        batch: builtins.list[FileIndexDraft] = []
        for root in resolved_roots:
            if not root.exists() or not root.is_dir():
                continue
            gitignore_cache: dict[Path, builtins.list[str]] = {}
            for file_path in self._walk_files(root):
                if self._should_ignore(file_path, root, gitignore_cache):
                    skipped += 1
                    continue
                try:
                    raw_text, file_stat = self._read_rooted_regular_file(root, file_path)
                except (OSError, UnicodeDecodeError, ValueError):
                    skipped += 1
                    continue
                relative_path = file_path.as_posix()
                seen_paths.add(relative_path)
                content_hash = self._hash_text(raw_text)
                existing = self._repository.get_by_path(project=resolved_project, path=relative_path)
                if (
                    not force
                    and
                    existing is not None
                    and existing.content_hash == content_hash
                    and existing.file_size == file_stat.st_size
                    and existing.mtime_ns == file_stat.st_mtime_ns
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
                document_id = existing.id if existing is not None else uuid7_str()
                batch.append(
                    FileIndexDraft(
                        document_id=document_id,
                        project=resolved_project,
                        path=relative_path,
                        root_path=root.as_posix(),
                        language=language,
                        metatags={},
                        file_size=file_stat.st_size,
                        content_hash=content_hash,
                        mtime_ns=file_stat.st_mtime_ns,
                        chunks=chunks,
                    )
                )
                indexed += 1
                if len(batch) >= 100:
                    self._flush_index_batch(batch)
                    batch.clear()
        if batch:
            self._flush_index_batch(batch)
            batch.clear()
        for root_paths in self._chunk_values([root.as_posix() for root in resolved_roots], size=128):
            for record in self._repository.list_indexed_files(project=resolved_project, root_paths=root_paths):
                if record.path not in seen_paths:
                    self._repository.delete(record.id, project=resolved_project)
                    deleted += 1
        if indexed > 0:
            self._drain_pending_embeddings(resolved_project, limit=1, time_budget_seconds=0.1)
        return FilesIndexResult(count=indexed + deleted, indexed=indexed, skipped=skipped, deleted=deleted)

    def reindex(self, roots: builtins.list[str] | None = None, *, project: str | None = None) -> FilesIndexResult:
        """Rebuild the derived file index, including chunks and embeddings."""
        resolved_project = project or self._project
        result = self.index(roots=roots, project=resolved_project, force=True)
        if self._embedding_service is not None and hasattr(self._repository, "pending_embedding_documents"):
            while self._repository.pending_embedding_documents(project=resolved_project, limit=1):
                self._drain_pending_embeddings(resolved_project, limit=32)
        return result

    def _resolve_roots(self, roots: builtins.list[str] | None, project: str) -> builtins.list[Path]:
        configured_roots = roots or self._roots
        if configured_roots:
            return [Path(root).expanduser().resolve() for root in configured_roots]
        if hasattr(self._repository, "list_indexed_root_paths"):
            indexed_roots = self._repository.list_indexed_root_paths(project=project)
            if indexed_roots:
                return [Path(root).expanduser().resolve() for root in indexed_roots]
        return [Path.cwd()]

    def list(
        self,
        limit: int = 20,
        *,
        project: str | None = None,
        cursor: str | None = None,
        view: str = "compact",
        root: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> FilesListResult:
        limit = validate_retrieval_limit(limit)
        resolved_project = project or self._project
        resolved_root = self._normalize_root(root)
        resolved_language = self._normalize_language(language)
        resolved_path_prefix = self._normalize_path_prefix(path_prefix, resolved_root)
        cursor_data = self._decode_cursor(cursor)
        cursor_id = cursor_data
        files = self._repository.list_indexed_files(
            project=resolved_project,
            root_path=resolved_root,
            language=resolved_language,
            path_prefix=resolved_path_prefix,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        next_cursor = None
        if len(files) > limit:
            next_cursor = self._encode_cursor(files[limit - 1].id)
            files = files[:limit]
        projected_files: builtins.list[IndexedFileRecord | FileListItem] = []
        if view == "full":
            projected_files.extend(files)
        else:
            projected_files.extend(compact_file_item(file) for file in files)
        return FilesListResult(
            count=len(files),
            files=projected_files,
            next_cursor=next_cursor,
        )

    def get(
        self,
        file_id: str | None = None,
        *,
        path: str | None = None,
        project: str | None = None,
        root: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> FilesGetResult:
        if file_id is None and (path is None or not path.strip()):
            raise ValueError("files get requires --id or --path")
        resolved_project = project or self._project
        resolved_root = self._normalize_root(root)
        resolved_language = self._normalize_language(language)
        resolved_path_prefix = self._normalize_path_prefix(path_prefix, resolved_root)
        record = self._resolve_file_record(
            file_id=file_id,
            path=path,
            project=resolved_project,
            root=resolved_root,
        )
        if record is None:
            raise LookupError("file not found")
        if not self._file_matches_filters(
            record,
            root=resolved_root,
            language=resolved_language,
            path_prefix=resolved_path_prefix,
        ):
            raise LookupError("file not found")
        return FilesGetResult(file=record)

    def delete(
        self,
        file_id: str | None = None,
        *,
        path: str | None = None,
        project: str | None = None,
        root: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
    ) -> FilesGetResult:
        if file_id is None and (path is None or not path.strip()):
            raise ValueError("files delete requires --id or --path")
        resolved_project = project or self._project
        resolved_root = self._normalize_root(root)
        resolved_language = self._normalize_language(language)
        resolved_path_prefix = self._normalize_path_prefix(path_prefix, resolved_root)
        record = self._resolve_file_record(
            file_id=file_id,
            path=path,
            project=resolved_project,
            root=resolved_root,
        )
        if record is None:
            raise LookupError("file not found")
        if not self._file_matches_filters(
            record,
            root=resolved_root,
            language=resolved_language,
            path_prefix=resolved_path_prefix,
        ):
            raise LookupError("file not found")
        deleted = self._repository.delete(record.id, project=resolved_project)
        if deleted is None:
            raise LookupError("file not found")
        return FilesGetResult(file=deleted)

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        project: str | None = None,
        budget_tokens: int | None = None,
        view: str = "compact",
        explain: bool = False,
        root: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
        prefer_lexical_only: bool = False,
        query_embedding: builtins.list[float] | None = None,
    ) -> FilesSearchResult:
        self._require_non_empty(query, "query")
        limit = validate_retrieval_limit(limit)
        resolved_project = project or self._project
        resolved_root = self._normalize_root(root)
        resolved_language = self._normalize_language(language)
        resolved_path_prefix = self._normalize_path_prefix(path_prefix, resolved_root)
        if not prefer_lexical_only:
            self._drain_pending_embeddings(resolved_project)
        candidate_limit = min(max(limit * 4, limit), MAX_RETRIEVAL_LIMIT)
        candidates = self._collect_candidates(
            query,
            candidate_limit,
            resolved_project,
            root=resolved_root,
            language=resolved_language,
            path_prefix=resolved_path_prefix,
            prefer_lexical_only=prefer_lexical_only,
            query_embedding=query_embedding,
        )
        reranked_candidates = (
            self._rerank_candidates(query, candidates, project=resolved_project)
            if not prefer_lexical_only
            else candidates
        )
        deduplicated = self._deduplicate_by_file(reranked_candidates)
        trimmed = self._trim_to_budget(
            deduplicated,
            budget_tokens if budget_tokens is not None else self._budget_tokens,
        )
        results: builtins.list[FileSearchHit] = []
        for candidate in trimmed[:limit]:
            file_item: IndexedFileRecord | FileListItem = candidate.file
            if view == "full":
                file_item = self._repository.get(candidate.file.id, project=resolved_project) or candidate.file
            results.append(
                FileSearchHit(
                    file=file_item,
                    chunk_id=candidate.chunk_id,
                    score=combine_search_scores(
                        lexical_score=candidate.lexical_score,
                        vector_score=candidate.vector_score,
                        rerank_score=candidate.rerank_score,
                    ),
                    snippet=candidate.snippet,
                )
            )
        stats = None
        if explain:
            stats = {
                "candidate_count": len(candidates),
                "deduplicated_count": len(deduplicated),
                "returned_count": len(results),
                "budget_tokens": budget_tokens if budget_tokens is not None else self._budget_tokens,
                "filters": {
                    "root": resolved_root,
                    "language": resolved_language,
                    "path_prefix": resolved_path_prefix,
                },
            }
        return FilesSearchResult(query=query, count=len(results), results=results, stats=stats)

    @staticmethod
    def _require_non_empty(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} must not be empty")

    def _queue_embeddings(self, document_id: str) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "enqueue_embedding_index"):
            return
        try:
            self._repository.enqueue_embedding_index(document_id)
        except Exception:
            return

    def _flush_index_batch(self, batch: builtins.list[FileIndexDraft]) -> None:
        if not batch:
            return
        for draft in batch:
            self._validate_metatags("files", draft.metatags)
        self._repository.upsert_files(batch)
        for draft in batch:
            self._queue_embeddings(draft.document_id)

    def _drain_pending_embeddings(
        self,
        project: str,
        *,
        limit: int = 8,
        time_budget_seconds: float | None = None,
    ) -> None:
        if self._embedding_service is None or not hasattr(self._repository, "pending_embedding_documents"):
            return
        try:
            pending_documents = self._repository.pending_embedding_documents(project=project, limit=limit)
        except Exception:
            return
        started_at = monotonic()
        for document_id in pending_documents:
            if time_budget_seconds is not None and monotonic() - started_at >= time_budget_seconds:
                break
            try:
                chunks = self._repository.list_chunks(document_id)
                if not chunks:
                    if hasattr(self._repository, "mark_embedding_index_ready"):
                        self._repository.mark_embedding_index_ready(document_id)
                    continue
                result = self._embedding_service.embed_chunks(
                    [chunk.id for chunk in chunks],
                    [chunk.chunk_text for chunk in chunks],
                    project=project,
                )
                self._repository.store_chunk_embeddings(
                    result.embeddings,
                    project=chunks[0].project,
                    metatags=self._serialize_metatags({}),
                    created_at=chunks[0].created_at,
                )
                if hasattr(self._repository, "mark_embedding_index_ready"):
                    self._repository.mark_embedding_index_ready(document_id)
            except Exception as exc:
                if hasattr(self._repository, "mark_embedding_index_error"):
                    self._repository.mark_embedding_index_error(
                        document_id,
                        last_error=safe_provider_error("embeddings", exc),
                    )

    def _collect_candidates(
        self,
        query: str,
        limit: int,
        project: str,
        *,
        root: str | None = None,
        language: str | None = None,
        path_prefix: str | None = None,
        prefer_lexical_only: bool = False,
        query_embedding: builtins.list[float] | None = None,
    ) -> builtins.list[FileSearchCandidate]:
        lexical_rows = self._repository.search_lexical_candidates(
            query=query,
            limit=limit,
            project=project,
            root_path=root,
            language=language,
            path_prefix=path_prefix,
        )
        semantic_rows: builtins.list[FileSearchCandidate] = []
        resolved_query_embedding = query_embedding
        if resolved_query_embedding is None and self._embedding_service is not None and not prefer_lexical_only:
            try:
                resolved_query_embedding = self._embedding_service.embed_texts(
                    [query], projects=[project]
                ).embeddings[0].embedding
            except Exception:
                resolved_query_embedding = None
        if resolved_query_embedding is not None and not prefer_lexical_only:
            semantic_rows = self._repository.search_vector_candidates(
                query_embedding=resolved_query_embedding,
                limit=limit,
                project=project,
                root_path=root,
                language=language,
                path_prefix=path_prefix,
            )
        merged: OrderedDict[str, FileSearchCandidate] = OrderedDict()
        for candidate in [*lexical_rows, *semantic_rows]:
            current = merged.get(candidate.chunk_id)
            if current is None:
                merged[candidate.chunk_id] = candidate
                continue
            current.lexical_score = max(current.lexical_score, candidate.lexical_score)
            if candidate.vector_score is not None:
                current.vector_score = (
                    candidate.vector_score
                    if current.vector_score is None
                    else max(current.vector_score, candidate.vector_score)
                )
            if candidate.snippet and len(candidate.snippet) > len(current.snippet):
                current.snippet = candidate.snippet
            current.token_count = max(current.token_count, candidate.token_count)
        filtered = [
            candidate
            for candidate in merged.values()
            if self._file_matches_filters(
                candidate.file,
                root=root,
                language=language,
                path_prefix=path_prefix,
            )
        ]
        return sorted(
            filtered,
            key=lambda candidate: combine_search_scores(
                lexical_score=candidate.lexical_score,
                vector_score=candidate.vector_score,
                rerank_score=None,
            ),
            reverse=True,
        )[:limit]

    def _rerank_candidates(
        self,
        query: str,
        candidates: builtins.list[FileSearchCandidate],
        *,
        project: str,
    ) -> builtins.list[FileSearchCandidate]:
        if not candidates:
            return []
        if self._rerank_service is None:
            return candidates
        try:
            rerank_scores = self._rerank_service.rerank(
                query,
                [candidate.snippet for candidate in candidates],
                project=project,
            )
        except Exception:
            return candidates
        for candidate, rerank_score in zip(candidates, rerank_scores, strict=True):
            candidate.rerank_score = rerank_score
        return candidates

    def _deduplicate_by_file(self, candidates: builtins.list[FileSearchCandidate]) -> builtins.list[FileSearchCandidate]:
        best_by_file: OrderedDict[str, FileSearchCandidate] = OrderedDict()
        for candidate in candidates:
            key = candidate.file.id
            current = best_by_file.get(key)
            score = combine_search_scores(
                lexical_score=candidate.lexical_score,
                vector_score=candidate.vector_score,
                rerank_score=candidate.rerank_score,
            )
            if current is None:
                best_by_file[key] = candidate
                continue
            current_score = combine_search_scores(
                lexical_score=current.lexical_score,
                vector_score=current.vector_score,
                rerank_score=current.rerank_score,
            )
            if score > current_score:
                best_by_file[key] = candidate
        return list(best_by_file.values())

    def _walk_files(self, root: Path):
        for current in root.rglob("*"):
            if current.is_dir():
                continue
            yield current

    def _read_rooted_regular_file(self, root: Path, path: Path) -> tuple[str, os.stat_result]:
        relative = path.relative_to(root)
        if not relative.parts:
            raise ValueError("file path must be below the configured root")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(root, directory_flags | nofollow)
        opened_fds = [root_fd]
        try:
            directory_fd = root_fd
            for component in relative.parts[:-1]:
                next_fd = os.open(component, directory_flags | nofollow, dir_fd=directory_fd)
                opened_fds.append(next_fd)
                directory_fd = next_fd
            file_fd = os.open(
                relative.parts[-1],
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0) | nofollow,
                dir_fd=directory_fd,
            )
            opened_fds.append(file_fd)
            metadata = os.fstat(file_fd)
            if not stat_module.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("indexed path must be a regular, single-link file")
            if metadata.st_size > self._max_file_size:
                raise ValueError("indexed file exceeds configured size limit")
            chunks: builtins.list[bytes] = []
            remaining = self._max_file_size + 1
            while remaining > 0:
                chunk = os.read(file_fd, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > self._max_file_size or b"\x00" in raw[:4096]:
                raise ValueError("indexed file is oversized or binary")
            return raw.decode("utf-8"), metadata
        finally:
            for descriptor in reversed(opened_fds):
                os.close(descriptor)

    def _should_ignore(self, path: Path, root: Path, gitignore_cache: dict[Path, builtins.list[str]]) -> bool:
        relative_path = path.relative_to(root).as_posix()
        candidate_dirs = [root, *path.parents]
        patterns = list(self._ignore_patterns)
        for directory in candidate_dirs:
            if directory == root.parent:
                break
            if directory.is_dir() and directory not in gitignore_cache:
                gitignore_path = directory / ".gitignore"
                try:
                    gitignore_text, _ = self._read_rooted_regular_file(root, gitignore_path)
                except (OSError, UnicodeDecodeError, ValueError):
                    gitignore_cache[directory] = []
                else:
                    gitignore_cache[directory] = [
                        line.strip()
                        for line in gitignore_text.splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                    ]
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
    def _normalize_root(root: str | None) -> str | None:
        if root is None or not root.strip():
            return None
        return Path(root).expanduser().resolve().as_posix()

    @staticmethod
    def _normalize_language(language: str | None) -> str | None:
        if language is None or not language.strip():
            return None
        return language.strip().lower()

    @staticmethod
    def _normalize_path_prefix(path_prefix: str | None, root: str | None = None) -> str | None:
        if path_prefix is None or not path_prefix.strip():
            return None
        candidate = Path(path_prefix).expanduser()
        if candidate.is_absolute():
            return candidate.resolve().as_posix()
        base = Path(root).expanduser() if root is not None else Path.cwd()
        return (base / candidate).resolve().as_posix()

    @staticmethod
    def _normalize_scoped_path(path: str, root: str | None) -> str:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve().as_posix()
        base = Path(root).expanduser() if root is not None else Path.cwd()
        return (base / candidate).resolve().as_posix()

    @staticmethod
    def _encode_cursor(file_id: str) -> str:
        payload = json.dumps({"id": file_id}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> str | None:
        if cursor is None or not cursor.strip():
            return None
        padding = "=" * (-len(cursor) % 4)
        try:
            raw_value = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii")).decode("utf-8")
            payload = json.loads(raw_value)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("cursor must be an opaque pagination token") from exc
        if not isinstance(payload, dict):
            raise ValueError("cursor must be an opaque pagination token")
        file_id = payload.get("id")
        if isinstance(file_id, str) and file_id:
            return file_id
        path = payload.get("path")
        if not isinstance(path, str) or not path or not isinstance(file_id, str) or not file_id:
            raise ValueError("cursor must be an opaque pagination token")
        return file_id

    def _resolve_file_record(
        self,
        *,
        file_id: str | None,
        path: str | None,
        project: str,
        root: str | None,
    ):
        if path is not None and path.strip():
            return self._repository.get_by_path(
                project=project,
                path=self._normalize_scoped_path(path, root),
            )
        return self._repository.get(file_id or "", project=project)

    @staticmethod
    def _file_matches_filters(
        file: FileSearchCandidate | FileSearchHit | FilesGetResult | object,
        *,
        root: str | None,
        language: str | None,
        path_prefix: str | None,
    ) -> bool:
        file_obj = getattr(file, "file", file)
        file_root = getattr(file_obj, "root_path", None)
        file_language = getattr(file_obj, "language", None)
        file_path = getattr(file_obj, "path", None)
        if root is not None and file_root != root:
            return False
        if language is not None and str(file_language).lower() != language:
            return False
        if path_prefix is not None and (file_path is None or not str(file_path).startswith(path_prefix)):
            return False
        return True

    def _trim_to_budget(
        self,
        results: builtins.list[FileSearchCandidate],
        budget_tokens: int,
    ) -> builtins.list[FileSearchCandidate]:
        if budget_tokens <= 0:
            return []
        trimmed: builtins.list[FileSearchCandidate] = []
        total_tokens = 0
        for result in results:
            result_cost = self._estimate_result_tokens(result)
            if trimmed and total_tokens + result_cost > budget_tokens:
                break
            trimmed.append(result)
            total_tokens += result_cost
        return trimmed

    @staticmethod
    def _estimate_result_tokens(result: FileSearchCandidate) -> int:
        return max(
            1,
            count_tokens(result.file.path) + count_tokens(result.file.root_path) + count_tokens(result.snippet),
        )

    @staticmethod
    def _serialize_metatags(metatags: dict[str, object]) -> str:
        return json.dumps(metatags, ensure_ascii=False, separators=(",", ":"))

    def _validate_metatags(self, entity_type: str, metatags: dict[str, object]) -> None:
        if self._metadata_service is None:
            return
        self._metadata_service.validate(entity_type, metatags)

    @staticmethod
    def _chunk_values(values: builtins.list[str], *, size: int) -> builtins.list[builtins.list[str]]:
        if size <= 0:
            raise ValueError("size must be greater than zero")
        return [values[index : index + size] for index in range(0, len(values), size)]
