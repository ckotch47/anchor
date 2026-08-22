from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    default_view: str = "compact"
    default_limit: int = 20
    default_project: str = "workspace"
    default_budget_tokens: int = 800
    retry_attempts: int = 3
    busy_timeout_ms: int = 250
    offline_only: bool = True
    memory_auto_extract: bool = False
    memory_external_send: bool = False
    memory_external_projects: list[str] = Field(default_factory=list)
    embedding_external_send: bool = False
    embedding_external_projects: list[str] = Field(default_factory=list)
    rerank_external_send: bool = False
    rerank_external_projects: list[str] = Field(default_factory=list)
    memory_extract_batch_size: int = Field(default=10, gt=0)
    memory_extract_max_facts: int = Field(default=20, gt=0)
    memory_extract_min_interval_seconds: float = Field(default=60.0, ge=0.0)


class ProviderConfig(BaseModel):
    base_url: str = "https://api.example.com/v1"
    rerank_base_url: str = ""
    rerank_api_key_env: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    embedding_model: str = ""
    rerank_model: str = ""
    memory_model: str = ""
    rerank_max_response_bytes: int = Field(default=1_048_576, gt=0)
    max_batch_items: int = Field(default=100, gt=0, le=1_000)
    max_batch_characters: int = Field(default=200_000, gt=0, le=10_000_000)


class MetadataFieldConfig(BaseModel):
    type: Literal["string", "integer", "number", "boolean", "object", "array"] = "string"
    required: bool = False


class MetadataEntityConfig(BaseModel):
    allow_extra: bool = True
    fields: dict[str, MetadataFieldConfig] = Field(default_factory=dict)


class MetadataConfig(BaseModel):
    enabled: bool = True
    entities: dict[str, MetadataEntityConfig] = Field(default_factory=dict)


class LinksConfig(BaseModel):
    relation_types: list[str] = Field(
        default_factory=lambda: [
            "references",
            "blocks",
            "duplicates",
            "implements",
            "related",
            "caused_by",
            "derived_from",
        ]
    )


class VectorConfig(BaseModel):
    dimension: int = Field(default=1536, gt=0)
    distance: str = "cosine"
    chunk_size: int = Field(default=400, gt=0)
    chunk_overlap: int = Field(default=50, ge=0)


class FilesystemConfig(BaseModel):
    roots: list[str] = Field(default_factory=list)
    ignore_patterns: list[str] = Field(
        default_factory=lambda: [
            ".git/",
            "node_modules/",
            "dist/",
            "build/",
            "__pycache__/",
            "*.pyc",
        ]
    )
    max_file_size: int = Field(default=1_000_000, gt=0)
    refresh_policy: str = "mtime"


class ProfileConfig(BaseModel):
    view: str = "compact"
    limit: int = 20


class AppConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    links: LinksConfig = Field(default_factory=LinksConfig)
    vector: VectorConfig = Field(default_factory=VectorConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @classmethod
    def default(cls) -> AppConfig:
        return cls(
            profiles={
                "default": ProfileConfig(view="compact", limit=20),
                "full": ProfileConfig(view="full", limit=50),
            }
        )


def default_config_path() -> Path:
    return Path.home() / ".qatoria" / "anchor" / "config.toml"


def default_data_dir() -> Path:
    return Path.home() / ".qatoria" / "anchor"


def default_database_path() -> Path:
    return default_data_dir() / "anchor.sqlite3"


def ensure_private_default_data_dir() -> Path:
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = data_dir.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("Anchor data directory must be a real directory")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise PermissionError("Anchor data directory must be owned by the current user")
    data_dir.chmod(0o700)
    return data_dir
