from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from anchor.adapters.sqlite_ids import uuid7_str
from anchor.adapters.sqlite_repository import SqliteRepositoryBase
from anchor.adapters.sqlite_support import utc_now_iso
from anchor.application.memory.models import (
    MemoryFact,
    MemoryFactCreate,
    MemoryFactStatus,
    MemoryScenario,
    MemoryScope,
    MemoryScopeFilter,
)
from anchor.application.retrieval.search_query import normalize_fts5_query


class SqliteMemoryRepository(SqliteRepositoryBase):
    _EXTERNAL_EVIDENCE_PREFIXES = (
        "implementation:",
        "tests:",
        "smoke:",
        "migration:",
        "security:",
        "safety:",
        "metrics:",
        "release:",
    )

    def __init__(self, database_path: Path | None = None) -> None:
        super().__init__(database_path=database_path)

    def create(self, fact: MemoryFactCreate) -> MemoryFact:
        self._validate_scope_requirements(fact.scope, fact.project, fact.source_chat_id)
        if fact.supersedes_id is not None and fact.status != "active":
            raise ValueError("superseding memory facts must be active")
        fact_id = uuid7_str()
        now = utc_now_iso()
        with self._write_connect() as connection:
            if fact.supersedes_id is not None:
                previous = connection.execute(
                    "SELECT * FROM memory_facts WHERE id = ?",
                    (fact.supersedes_id,),
                ).fetchone()
                if previous is None:
                    raise LookupError(f"memory fact not found: {fact.supersedes_id}")
                if previous["status"] in {"deleted", "superseded"}:
                    raise ValueError("terminal memory fact cannot be superseded")
                if previous["scope"] != fact.scope or previous["fact_type"] != fact.fact_type:
                    raise ValueError("superseded fact must have the same scope and fact_type")
                if fact.scope == "project" and previous["project"] != fact.project:
                    raise ValueError("superseded project fact must belong to the same project")
                if fact.scope == "chat" and previous["source_chat_id"] != fact.source_chat_id:
                    raise ValueError("superseded chat fact must belong to the same chat")
                connection.execute(
                    "UPDATE memory_facts SET status = 'superseded', updated_at = ? WHERE id = ?",
                    (now, fact.supersedes_id),
                )
            connection.execute(
                """
                INSERT INTO memory_facts (
                    id, scope, project, source_chat_id, fact_type, content, confidence,
                    status, evidence_refs, valid_from, valid_until, supersedes_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    fact.scope,
                    fact.project,
                    fact.source_chat_id,
                    fact.fact_type,
                    fact.content,
                    fact.confidence,
                    fact.status,
                    json.dumps(fact.evidence_refs, ensure_ascii=False, separators=(",", ":")),
                    fact.valid_from,
                    fact.valid_until,
                    fact.supersedes_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO memory_facts_fts (fact_id, content) VALUES (?, ?)",
                (fact_id, fact.content),
            )
            connection.commit()
        result = self.get(fact_id)
        if result is None:
            raise RuntimeError("created memory fact could not be reloaded")
        return result

    def get(self, fact_id: str) -> MemoryFact | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
        return None if row is None else self._row_to_fact(row)

    def find_duplicate(self, fact: MemoryFactCreate) -> MemoryFact | None:
        self._validate_scope_requirements(fact.scope, fact.project, fact.source_chat_id)
        where = [
            "scope = ?",
            "fact_type = ?",
            "lower(trim(content)) = lower(trim(?))",
            "status IN ('candidate', 'active')",
        ]
        params: list[object] = [fact.scope, fact.fact_type, fact.content]
        if fact.scope == "project":
            where.append("project = ?")
            params.append(fact.project)
        elif fact.scope == "chat":
            where.append("source_chat_id = ?")
            params.append(fact.source_chat_id)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM memory_facts WHERE {' AND '.join(where)} ORDER BY status = 'active' DESC, updated_at DESC LIMIT 1",
                params,
            ).fetchone()
        return None if row is None else self._row_to_fact(row)

    def merge_duplicate(
        self,
        fact_id: str,
        *,
        evidence_refs: list[str | dict[str, object]],
        confidence: float,
        status: MemoryFactStatus,
    ) -> MemoryFact | None:
        current = self.get(fact_id)
        if current is None:
            return None
        merged_refs = list(current.evidence_refs)
        for ref in evidence_refs:
            if ref not in merged_refs:
                merged_refs.append(ref)
        merged_status = "active" if status == "active" else current.status
        with self._write_connect() as connection:
            connection.execute(
                "UPDATE memory_facts SET evidence_refs = ?, confidence = ?, status = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(merged_refs, ensure_ascii=False, separators=(",", ":")),
                    max(current.confidence, confidence),
                    merged_status,
                    utc_now_iso(),
                    fact_id,
                ),
            )
            connection.commit()
        return self.get(fact_id)

    def recent_history(
        self,
        *,
        project: str,
        after_updated_at: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        where = ["d.project = ?", "d.document_type = 'history'", "d.deleted_at IS NULL"]
        params: list[object] = [project]
        if after_updated_at:
            where.append("d.updated_at > ?")
            params.append(after_updated_at)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.id, d.updated_at, h.entry_type, h.payload
                FROM documents AS d
                JOIN history_entries AS h ON h.document_id = d.id
                WHERE {' AND '.join(where)}
                ORDER BY d.updated_at ASC, d.id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "updated_at": row["updated_at"],
                "entry_type": row["entry_type"],
                "payload": row["payload"],
            }
            for row in rows
        ]

    def get_checkpoint(self, *, project: str, chat_id: str | None) -> dict[str, object] | None:
        key = self._checkpoint_key(project, chat_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_pipeline_checkpoints WHERE pipeline_key = ?",
                (key,),
            ).fetchone()
        return None if row is None else dict(row)

    def save_checkpoint(
        self,
        *,
        project: str,
        chat_id: str | None,
        last_history_updated_at: str | None,
        processed_count: int,
        status: str,
        last_error: str | None = None,
    ) -> None:
        now = utc_now_iso()
        key = self._checkpoint_key(project, chat_id)
        with self._write_connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_pipeline_checkpoints (
                    pipeline_key, project, chat_id, last_history_updated_at, last_run_at,
                    processed_count, status, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pipeline_key) DO UPDATE SET
                    last_history_updated_at = excluded.last_history_updated_at,
                    last_run_at = excluded.last_run_at,
                    processed_count = memory_pipeline_checkpoints.processed_count + excluded.processed_count,
                    status = excluded.status,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (key, project, chat_id, last_history_updated_at, now, processed_count, status, last_error, now),
            )
            connection.commit()

    def get_batch_state(self, *, project: str, chat_id: str | None) -> dict[str, object] | None:
        checkpoint = self.get_checkpoint(project=project, chat_id=chat_id)
        if checkpoint is None:
            return None
        return {
            "pending_count": int(checkpoint.get("pending_count") or 0),
            "pending_since": checkpoint.get("pending_since"),
            "last_extraction_at": checkpoint.get("last_extraction_at"),
        }

    def save_batch_state(
        self,
        *,
        project: str,
        chat_id: str | None,
        pending_count: int,
        pending_since: float | None,
        last_extraction_at: float | None,
    ) -> None:
        now = utc_now_iso()
        key = self._checkpoint_key(project, chat_id)
        with self._write_connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_pipeline_checkpoints (
                    pipeline_key, project, chat_id, processed_count, status, updated_at,
                    pending_count, pending_since, last_extraction_at
                ) VALUES (?, ?, ?, 0, 'idle', ?, ?, ?, ?)
                ON CONFLICT(pipeline_key) DO UPDATE SET
                    pending_count = excluded.pending_count,
                    pending_since = excluded.pending_since,
                    last_extraction_at = excluded.last_extraction_at,
                    updated_at = excluded.updated_at
                """,
                (key, project, chat_id, now, pending_count, pending_since, last_extraction_at),
            )
            connection.commit()

    def create_scenario(
        self,
        *,
        scope: str,
        project: str | None,
        title: str,
        summary: str,
        fact_ids: list[str],
        evidence_refs: list[str],
    ) -> MemoryScenario:
        scenario_id = uuid7_str()
        now = utc_now_iso()
        with self._write_connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_scenarios (
                    id, scope, project, title, summary, fact_ids, evidence_refs,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    scenario_id,
                    scope,
                    project,
                    title,
                    summary,
                    json.dumps(fact_ids, separators=(",", ":")),
                    json.dumps(evidence_refs, separators=(",", ":")),
                    now,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO memory_scenarios_fts (scenario_id, title, summary) VALUES (?, ?, ?)",
                (scenario_id, title, summary),
            )
            connection.commit()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM memory_scenarios WHERE id = ?", (scenario_id,)).fetchone()
        if row is None:
            raise RuntimeError("created memory scenario could not be reloaded")
        return self._row_to_scenario(row)

    def search_scenarios(
        self,
        query: str,
        *,
        projects: list[str] | None = None,
        limit: int = 5,
    ) -> list[tuple[MemoryScenario, float, str]]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        normalized_query = normalize_fts5_query(query)
        if not normalized_query:
            raise ValueError("query must contain searchable text")
        where = ["s.status = 'active'", "memory_scenarios_fts MATCH ?"]
        params: list[object] = [normalized_query]
        if projects:
            placeholders = ", ".join("?" for _ in projects)
            where.append(f"(s.scope = 'global' OR (s.scope = 'project' AND s.project IN ({placeholders})))")
            params.extend(projects)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.*, bm25(memory_scenarios_fts) AS rank
                FROM memory_scenarios_fts
                JOIN memory_scenarios AS s ON s.id = memory_scenarios_fts.scenario_id
                WHERE {' AND '.join(where)}
                ORDER BY rank ASC, s.updated_at DESC, s.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            (self._row_to_scenario(row), self._rank_to_score(float(row["rank"])), self._snippet(row["summary"], query))
            for row in rows
        ]

    def active_conflicts(
        self,
        *,
        project: str,
        chat_id: str | None = None,
        limit: int = 20,
    ) -> list[tuple[MemoryScope, str | None, str | None, str, list[MemoryFact]]]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        where = [
            "status = 'conflicted'",
            "(scope = 'global' OR (scope = 'project' AND project = ?) OR (scope = 'chat' AND source_chat_id = ?))",
        ]
        params: list[object] = [project, chat_id or ""]
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM memory_facts WHERE {' AND '.join(where)} ORDER BY fact_type, scope, project, source_chat_id, updated_at DESC",
                params,
            ).fetchall()
        grouped: dict[tuple[str, str | None, str | None, str], list[MemoryFact]] = {}
        for row in rows:
            fact = self._row_to_fact(row)
            key = (fact.scope, fact.project if fact.scope == "project" else None, fact.source_chat_id if fact.scope == "chat" else None, fact.fact_type)
            grouped.setdefault(key, []).append(fact)
        conflicts = []
        for (scope, fact_project, source_chat_id, fact_type), facts in grouped.items():
            contents = {fact.content.casefold().strip() for fact in facts}
            if len(contents) > 1:
                conflicts.append((scope, fact_project, source_chat_id, fact_type, facts))
        return conflicts[:limit]

    def metrics(self, *, project: str) -> dict[str, object]:
        with self._connect() as connection:
            fact_rows = connection.execute(
                "SELECT status, evidence_refs, scope, project FROM memory_facts WHERE scope = 'global' OR project = ?",
                (project,),
            ).fetchall()
            scenario_rows = connection.execute(
                "SELECT status FROM memory_scenarios WHERE scope = 'global' OR project = ?",
                (project,),
            ).fetchall()
            checkpoint_rows = connection.execute(
                "SELECT status, pending_count FROM memory_pipeline_checkpoints WHERE project = ?",
                (project,),
            ).fetchall()
        facts_by_status: dict[str, int] = {}
        total_evidence_refs = 0
        broken_evidence_refs = 0
        external_evidence_refs = 0
        for row in fact_rows:
            status = str(row["status"])
            facts_by_status[status] = facts_by_status.get(status, 0) + 1
            refs = self._decode_evidence_refs(row["evidence_refs"])
            total_evidence_refs += len(refs)
            source_project = row["project"] or project
            canonical_refs = []
            for ref in refs:
                if isinstance(ref, str) and ref.startswith(self._EXTERNAL_EVIDENCE_PREFIXES):
                    external_evidence_refs += 1
                else:
                    canonical_refs.append(ref)
            for item in self.get_evidence_records(canonical_refs, project=source_project):
                if not item["found"]:
                    broken_evidence_refs += 1
        scenarios_by_status: dict[str, int] = {}
        for row in scenario_rows:
            status = str(row["status"])
            scenarios_by_status[status] = scenarios_by_status.get(status, 0) + 1
        checkpoints: dict[str, int] = {}
        pending_extraction_count = 0
        for row in checkpoint_rows:
            status = str(row["status"])
            checkpoints[status] = checkpoints.get(status, 0) + 1
            pending_extraction_count += int(row["pending_count"] or 0)
        return {
            "project": project,
            "facts_by_status": facts_by_status,
            "scenarios_by_status": scenarios_by_status,
            "conflicted_facts": facts_by_status.get("conflicted", 0),
            "total_evidence_refs": total_evidence_refs,
            "broken_evidence_refs": broken_evidence_refs,
            "broken_canonical_evidence_refs": broken_evidence_refs,
            "external_evidence_refs": external_evidence_refs,
            "pending_extraction_count": pending_extraction_count,
            "checkpoints": checkpoints,
        }

    @staticmethod
    def _checkpoint_key(project: str, chat_id: str | None) -> str:
        return f"{project}\x00{chat_id or ''}"

    def update_status(self, fact_id: str, status: MemoryFactStatus) -> MemoryFact | None:
        now = utc_now_iso()
        with self._write_connect() as connection:
            cursor = connection.execute(
                "UPDATE memory_facts SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, fact_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            return None
        return self.get(fact_id)

    def update_scope(
        self,
        fact_id: str,
        *,
        scope: MemoryScope,
        project: str | None,
        source_chat_id: str | None,
    ) -> MemoryFact | None:
        self._validate_scope_requirements(scope, project, source_chat_id)
        now = utc_now_iso()
        with self._write_connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_facts
                SET scope = ?, project = ?, source_chat_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (scope, project, source_chat_id, now, fact_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            return None
        return self.get(fact_id)

    def search(
        self,
        query: str,
        *,
        scope: MemoryScopeFilter = "all",
        projects: list[str] | None = None,
        chat_id: str | None = None,
        fact_type: str | None = None,
        statuses: list[MemoryFactStatus] | None = None,
        limit: int = 20,
    ) -> list[tuple[MemoryFact, float, str]]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        normalized_query = normalize_fts5_query(query)
        if not normalized_query:
            raise ValueError("query must contain searchable text")
        where: list[str] = ["f.status != 'deleted'", "memory_facts_fts MATCH ?"]
        params: list[object] = [normalized_query]
        self._append_scope_filter(where, params, scope=scope, projects=projects, chat_id=chat_id)
        if fact_type is not None:
            where.append("f.fact_type = ?")
            params.append(fact_type)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where.append(f"f.status IN ({placeholders})")
            params.extend(statuses)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT f.*, bm25(memory_facts_fts) AS rank
                FROM memory_facts_fts
                JOIN memory_facts AS f ON f.id = memory_facts_fts.fact_id
                WHERE {' AND '.join(where)}
                ORDER BY rank ASC, f.updated_at DESC, f.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            (self._row_to_fact(row), self._rank_to_score(float(row["rank"])), self._snippet(row["content"], query))
            for row in rows
        ]

    def list_evidence(self, fact_id: str) -> list[str | dict[str, object]]:
        fact = self.get(fact_id)
        return [] if fact is None else fact.evidence_refs

    def get_evidence_records(
        self,
        evidence_refs: list[str | dict[str, object]],
        *,
        project: str,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        with self._connect() as connection:
            for reference in evidence_refs:
                reference_id = reference.get("id") if isinstance(reference, dict) else reference
                if not isinstance(reference_id, str) or not reference_id.strip():
                    records.append({"reference": reference, "found": False, "record": None})
                    continue
                row = connection.execute(
                    """
                    SELECT d.id, d.project, d.document_type, d.title, d.body, d.source, d.source_ref,
                           d.created_at, d.updated_at, h.entry_type, h.actor, h.payload,
                           n.note_kind, t.status AS task_status, t.task_kind,
                           f.path, f.root_path, f.language
                    FROM documents AS d
                    LEFT JOIN history_entries AS h ON h.document_id = d.id
                    LEFT JOIN notes AS n ON n.document_id = d.id
                    LEFT JOIN tasks AS t ON t.document_id = d.id
                    LEFT JOIN indexed_files AS f ON f.document_id = d.id
                    WHERE d.id = ? AND d.project = ? AND d.deleted_at IS NULL
                    """,
                    (reference_id, project),
                ).fetchone()
                kind = str(reference.get("type", "document")) if isinstance(reference, dict) else "document"
                if row is not None:
                    record = dict(row)
                    record["kind"] = kind
                    records.append({"reference": reference, "found": True, "record": record})
                    continue
                row = connection.execute(
                    """
                    SELECT c.id, c.document_id, d.project, d.document_type, d.title,
                           c.chunk_index, c.chunk_text, c.token_count, c.created_at
                    FROM document_chunks AS c
                    JOIN documents AS d ON d.id = c.document_id
                    WHERE c.id = ? AND d.project = ? AND d.deleted_at IS NULL
                    """,
                    (reference_id, project),
                ).fetchone()
                if row is None:
                    row = connection.execute(
                        """
                        SELECT c.id, c.document_id, c.project, d.document_type, d.title,
                               c.path, c.root_path, c.language, c.chunk_index, c.start_line,
                               c.end_line, c.chunk_text, c.token_count, c.created_at
                        FROM file_chunks AS c
                        JOIN documents AS d ON d.id = c.document_id
                        WHERE c.id = ? AND c.project = ? AND d.deleted_at IS NULL
                        """,
                        (reference_id, project),
                    ).fetchone()
                if row is None:
                    records.append({"reference": reference, "found": False, "record": None})
                else:
                    record = dict(row)
                    record["kind"] = kind if kind != "document" else "chunk"
                    records.append({"reference": reference, "found": True, "record": record})
        return records

    def invalidate_by_evidence(self, evidence_ids: list[str]) -> int:
        if not evidence_ids:
            return 0
        with self._write_connect() as connection:
            rows = connection.execute(
                "SELECT id, evidence_refs FROM memory_facts WHERE status != 'deleted'"
            ).fetchall()
            invalidated = 0
            now = utc_now_iso()
            for row in rows:
                refs = self._decode_evidence_refs(row["evidence_refs"])
                ref_ids = {ref if isinstance(ref, str) else str(ref.get("id", "")) for ref in refs}
                if ref_ids.intersection(evidence_ids):
                    connection.execute(
                        "UPDATE memory_facts SET status = 'deleted', updated_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    invalidated += 1
            connection.commit()
        return invalidated

    @staticmethod
    def _validate_scope_requirements(scope: MemoryScope, project: str | None, chat_id: str | None) -> None:
        if scope == "global" and chat_id is None and project is None:
            return
        if scope == "project" and not project:
            raise ValueError("project scope requires project")
        if scope == "chat" and not chat_id:
            raise ValueError("chat scope requires source_chat_id")

    @staticmethod
    def _append_scope_filter(
        where: list[str],
        params: list[object],
        *,
        scope: MemoryScopeFilter,
        projects: list[str] | None,
        chat_id: str | None,
    ) -> None:
        if scope == "global":
            where.append("f.scope = 'global'")
        elif scope == "project":
            where.append("f.scope = 'project'")
            SqliteMemoryRepository._append_projects(where, params, projects)
        elif scope == "chat":
            where.append("f.scope = 'chat'")
            if not chat_id:
                raise ValueError("chat scope requires chat_id")
            where.append("f.source_chat_id = ?")
            params.append(chat_id)
        elif scope == "all":
            if projects or chat_id:
                branches = ["f.scope = 'global'"]
                branch_params: list[object] = []
                if projects:
                    placeholders = ", ".join("?" for _ in projects)
                    branches.append(f"(f.scope = 'project' AND f.project IN ({placeholders}))")
                    branch_params.extend(projects)
                if chat_id:
                    branches.append("(f.scope = 'chat' AND f.source_chat_id = ?)")
                    branch_params.append(chat_id)
                where.append("(" + " OR ".join(branches) + ")")
                params.extend(branch_params)
        else:
            raise ValueError(f"unsupported memory scope: {scope}")

    @staticmethod
    def _append_projects(where: list[str], params: list[object], projects: list[str] | None) -> None:
        if not projects:
            return
        placeholders = ", ".join("?" for _ in projects)
        where.append(f"f.project IN ({placeholders})")
        params.extend(projects)

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> MemoryFact:
        return MemoryFact(
            id=row["id"],
            scope=row["scope"],
            project=row["project"],
            source_chat_id=row["source_chat_id"],
            fact_type=row["fact_type"],
            content=row["content"],
            confidence=float(row["confidence"]),
            status=row["status"],
            evidence_refs=SqliteMemoryRepository._decode_evidence_refs(row["evidence_refs"]),
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            supersedes_id=row["supersedes_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_scenario(row: sqlite3.Row) -> MemoryScenario:
        return MemoryScenario(
            id=row["id"],
            scope=row["scope"],
            project=row["project"],
            title=row["title"],
            summary=row["summary"],
            fact_ids=json.loads(row["fact_ids"] or "[]"),
            evidence_refs=json.loads(row["evidence_refs"] or "[]"),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _decode_evidence_refs(value: str) -> list[str | dict[str, object]]:
        decoded = json.loads(value or "[]")
        if not isinstance(decoded, list):
            raise ValueError("evidence_refs must be a JSON array")
        return decoded

    @staticmethod
    def _rank_to_score(rank: float) -> float:
        return 1.0 / (1.0 + abs(rank))

    @staticmethod
    def _snippet(content: str, query: str) -> str:
        lowered = content.lower()
        term = next((part.lower() for part in query.split() if part.strip()), "")
        position = lowered.find(term) if term else -1
        if position < 0:
            return content[:240]
        start = max(0, position - 80)
        return content[start : start + 240]


def invalidate_memory_facts_for_evidence(database_path: Path, evidence_ids: list[str]) -> int:
    """Invalidate derived facts after a canonical document or file is deleted."""
    repository = SqliteMemoryRepository(database_path=database_path)
    expanded_ids = set(evidence_ids)
    with repository._connect() as connection:
        placeholders = ", ".join("?" for _ in evidence_ids)
        if placeholders:
            rows = connection.execute(
                f"""
                SELECT id FROM document_chunks WHERE document_id IN ({placeholders})
                UNION ALL
                SELECT id FROM file_chunks WHERE document_id IN ({placeholders})
                """,
                [*evidence_ids, *evidence_ids],
            ).fetchall()
            expanded_ids.update(str(row[0]) for row in rows)
    return repository.invalidate_by_evidence(sorted(expanded_ids))
