from __future__ import annotations

import json

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso


class SqliteProviderEgressAuditRepository(SqliteRepositoryBase):
    def record(
        self,
        *,
        provider_kind: str,
        endpoint_host: str,
        model: str,
        projects: list[str],
        item_count: int,
        outcome: str,
        error_type: str = "",
    ) -> None:
        payload = {
            "provider_kind": provider_kind,
            "endpoint_host": endpoint_host,
            "model": model,
            "projects": sorted(set(projects)),
            "item_count": item_count,
            "outcome": outcome,
            "error_type": error_type,
        }
        with self._write_connect() as connection:
            connection.execute(
                "INSERT INTO events (id, entity_type, entity_id, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    uuid7_str(),
                    "provider",
                    provider_kind,
                    "provider_egress",
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    utc_now_iso(),
                ),
            )
            connection.commit()
