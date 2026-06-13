from __future__ import annotations

import copy
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from anchor import config as config_module
from anchor.config import AppConfig


class FileSystemConfigRepository:
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
        if not self._config_path.exists():
            return AppConfig.default(), self._config_path

        raw = self._config_path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8")) if raw else {}
        config = AppConfig.model_validate(data or {})
        return config, self._config_path

    def save(self, config: AppConfig) -> Path:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
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
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise
        return self._config_path

    def init_from_example(self, force: bool = False) -> tuple[AppConfig, Path]:
        if self._config_path.exists() and not force:
            raise FileExistsError(f"config already exists: {self._config_path}")
        example_path = self._example_path()
        if not example_path.exists():
            raise FileNotFoundError(f"config example not found: {example_path}")
        example_data = tomllib.loads(example_path.read_text(encoding="utf-8"))
        config = AppConfig.model_validate(example_data or {})
        self.save(config)
        return config, self._config_path

    def _serialize(self, config: AppConfig) -> str:
        lines: list[str] = []
        lines.extend(self._serialize_section("runtime", config.runtime.model_dump()))
        lines.append("")
        lines.extend(self._serialize_section("provider", config.provider.model_dump()))
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

    def _example_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "config.example.toml"
