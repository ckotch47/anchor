from __future__ import annotations

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


class ProviderConfig(BaseModel):
    base_url: str = "https://api.example.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    embedding_model: str = ""
    rerank_model: str = ""


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
