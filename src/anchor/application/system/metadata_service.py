from __future__ import annotations

from anchor.config import MetadataConfig, MetadataFieldConfig


class MetadataSchemaService:
    def __init__(self, config: MetadataConfig) -> None:
        self._config = config

    def validate(self, entity_type: str, metatags: dict[str, object]) -> None:
        if not self._config.enabled:
            return
        entity_schema = self._config.entities.get(entity_type)
        if entity_schema is None:
            return
        if not entity_schema.allow_extra:
            unexpected = sorted(key for key in metatags if key not in entity_schema.fields)
            if unexpected:
                raise ValueError(f"unsupported metatags for {entity_type}: {', '.join(unexpected)}")
        for field_name, field_schema in entity_schema.fields.items():
            if field_schema.required and field_name not in metatags:
                raise ValueError(f"missing required metatag: {field_name}")
            if field_name not in metatags:
                continue
            value = metatags[field_name]
            if not self._matches_type(value, field_schema):
                raise ValueError(
                    f"invalid metatag type for {entity_type}.{field_name}: expected {field_schema.type}"
                )

    @staticmethod
    def _matches_type(value: object, field_schema: MetadataFieldConfig) -> bool:
        match field_schema.type:
            case "string":
                return isinstance(value, str)
            case "integer":
                return isinstance(value, int) and not isinstance(value, bool)
            case "number":
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            case "boolean":
                return isinstance(value, bool)
            case "object":
                return isinstance(value, dict)
            case "array":
                return isinstance(value, list)
        return False
