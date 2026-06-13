from __future__ import annotations

from pydantic import BaseModel

from anchor.adapters.filesystem_config_repository import FileSystemConfigRepository
from anchor.config import AppConfig, ProfileConfig


class ConfigResult(BaseModel):
    config: AppConfig
    config_path: str
    profile_name: str | None


class ConfigService:
    def __init__(self, repository: FileSystemConfigRepository) -> None:
        self._repository = repository

    def get(self, profile: str | None = None) -> ConfigResult:
        config, config_path, profile_name = self._repository.load(profile=profile)
        return ConfigResult(
            config=config,
            config_path=str(config_path),
            profile_name=profile_name,
        )

    def set(
        self,
        section: str,
        key: str,
        value: str,
        profile: str | None = None,
    ) -> ConfigResult:
        config, config_path = self._repository.load_raw()
        match section:
            case "runtime":
                self._set_model_field(config.runtime, key, value)
            case "provider":
                self._set_model_field(config.provider, key, value)
            case "vector":
                self._set_model_field(config.vector, key, value)
            case "filesystem":
                self._set_model_field(config.filesystem, key, value)
            case "profiles":
                target_profile = profile or "default"
                profile_model = config.profiles.get(target_profile)
                if profile_model is None:
                    profile_model = ProfileConfig()
                    config.profiles[target_profile] = profile_model
                self._set_model_field(profile_model, key, value)
            case _:
                raise ValueError(f"Unsupported config section: {section}")

        self._repository.save(config)
        return ConfigResult(
            config=config,
            config_path=str(config_path),
            profile_name=profile,
        )

    def init(self, force: bool = False) -> ConfigResult:
        config, config_path = self._repository.init_from_example(force=force)
        return ConfigResult(
            config=config,
            config_path=str(config_path),
            profile_name=None,
        )

    def _set_model_field(self, model: BaseModel, key: str, raw_value: str) -> None:
        if key not in type(model).model_fields:
            raise ValueError(f"Unsupported config key: {key}")
        current = getattr(model, key)
        setattr(model, key, self._coerce_value(current, raw_value))

    @staticmethod
    def _coerce_value(current: object, raw_value: str) -> object:
        if isinstance(current, bool):
            return ConfigService._parse_bool(raw_value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(raw_value)
        if isinstance(current, float):
            return float(raw_value)
        if isinstance(current, list):
            stripped = raw_value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                import json

                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("invalid list value")
                return parsed
            return [item.strip() for item in raw_value.split(",") if item.strip()]
        return raw_value

    @staticmethod
    def _parse_bool(raw_value: str) -> bool:
        normalized = raw_value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        return False
