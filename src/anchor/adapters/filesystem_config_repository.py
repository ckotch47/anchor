from __future__ import annotations

import copy
import os
import stat
import tempfile
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

from anchor import config as config_module
from anchor.config import AppConfig


class FileSystemConfigRepository:
    _MAX_CONFIG_BYTES = 1_000_000

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or config_module.default_config_path()

    def load(self, profile: str | None = None) -> tuple[AppConfig, Path, str | None]:
        config, config_path = self.load_raw()
        if profile and profile in config.profiles:
            effective = copy.deepcopy(config)
            profile_config = effective.profiles[profile]
            effective.runtime.default_view = profile_config.view
            effective.runtime.default_limit = profile_config.limit
            return effective, config_path, profile
        return config, config_path, profile

    def load_raw(self) -> tuple[AppConfig, Path]:
        try:
            parent_metadata = os.lstat(self._config_path.parent)
        except FileNotFoundError:
            return AppConfig.default(), self._config_path
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or self._config_path.parent.is_symlink()
            or parent_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        ):
            raise ValueError("config parent must be a trusted private directory")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(self._config_path, flags)
        except FileNotFoundError:
            return AppConfig.default(), self._config_path
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise ValueError("config must be a trusted private regular file")
            chunks: list[bytes] = []
            remaining = self._MAX_CONFIG_BYTES + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > self._MAX_CONFIG_BYTES:
                raise ValueError("config exceeds maximum supported size")
            current = os.lstat(self._config_path)
            if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ValueError("config identity changed during read")
        finally:
            os.close(descriptor)
        data = tomllib.loads(raw.decode("utf-8")) if raw else {}
        config = AppConfig.model_validate(data or {})
        return config, self._config_path

    def save(self, config: AppConfig) -> Path:
        if self._config_path == config_module.default_config_path():
            config_module.ensure_private_default_data_dir()
        self._config_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent_metadata = os.lstat(self._config_path.parent)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or self._config_path.parent.is_symlink()
            or parent_metadata.st_uid != os.geteuid()
        ):
            raise ValueError("config parent must be an owned real directory")
        self._config_path.parent.chmod(0o700)
        payload = self._serialize(config)
        temp_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._config_path.parent,
            prefix=f".{self._config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        try:
            assert temp_path is not None
            temp_path.replace(self._config_path)
            self._config_path.chmod(0o600)
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise
        return self._config_path

    def init_from_example(self, force: bool = False) -> tuple[AppConfig, Path]:
        if self._config_path.exists() and not force:
            raise FileExistsError(f"config already exists: {self._config_path}")
        example_data = tomllib.loads(self._example_text())
        config = AppConfig.model_validate(example_data or {})
        self.save(config)
        return config, self._config_path

    def _serialize(self, config: AppConfig) -> str:
        lines: list[str] = []
        lines.extend(self._serialize_section("runtime", config.runtime.model_dump()))
        lines.append("")
        lines.extend(self._serialize_section("provider", config.provider.model_dump()))
        lines.append("")
        lines.extend(self._serialize_metadata_section(config))
        lines.append("")
        lines.extend(self._serialize_section("links", config.links.model_dump()))
        lines.append("")
        lines.extend(self._serialize_section("vector", config.vector.model_dump()))
        lines.append("")
        lines.extend(self._serialize_section("filesystem", config.filesystem.model_dump()))
        if config.profiles:
            lines.append("")
            for profile_name in sorted(config.profiles):
                lines.append(f"[profiles.{profile_name}]")
                lines.extend(self._serialize_key_values(config.profiles[profile_name].model_dump()))
                lines.append("")
            if lines and lines[-1] == "":
                lines.pop()
        return "\n".join(line for line in lines if line is not None).rstrip() + "\n"

    def _serialize_metadata_section(self, config: AppConfig) -> list[str]:
        lines = ["[metadata]"]
        lines.append(f"enabled = {self._format_value(config.metadata.enabled)}")
        if config.metadata.entities:
            lines.append("")
            for entity_name in sorted(config.metadata.entities):
                entity = config.metadata.entities[entity_name]
                lines.append(f"[metadata.entities.{entity_name}]")
                lines.append(f"allow_extra = {self._format_value(entity.allow_extra)}")
                if entity.fields:
                    lines.append("")
                    for field_name in sorted(entity.fields):
                        field = entity.fields[field_name]
                        lines.append(f"[metadata.entities.{entity_name}.fields.{field_name}]")
                        lines.append(f"type = {self._format_value(field.type)}")
                        lines.append(f"required = {self._format_value(field.required)}")
                        lines.append("")
                    if lines and lines[-1] == "":
                        lines.pop()
                lines.append("")
            if lines and lines[-1] == "":
                lines.pop()
        return lines

    def _serialize_section(self, name: str, data: dict[str, Any]) -> list[str]:
        lines = [f"[{name}]"]
        lines.extend(self._serialize_key_values(data))
        return lines

    def _serialize_key_values(self, data: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for key, value in data.items():
            lines.append(f"{key} = {self._format_value(value)}")
        return lines

    def _format_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[" + ", ".join(self._format_value(item) for item in value) + "]"
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _example_text(self) -> str:
        package_example = resources.files("anchor").joinpath("config.example.toml")
        if package_example.is_file():
            return package_example.read_text(encoding="utf-8")
        repo_example = Path(__file__).resolve().parents[3] / "config.example.toml"
        if repo_example.exists():
            return repo_example.read_text(encoding="utf-8")
        raise FileNotFoundError(f"config example not found: {package_example}")
