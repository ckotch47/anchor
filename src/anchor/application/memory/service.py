from __future__ import annotations

from anchor.adapters.sqlite_memory_repository import SqliteMemoryRepository
from anchor.application.memory.models import (
    MemoryConflictGroup,
    MemoryConflictResult,
    MemoryContextResult,
    MemoryEvidenceItem,
    MemoryEvidenceResult,
    MemoryFact,
    MemoryFactCreate,
    MemoryFactStatus,
    MemoryMetricsResult,
    MemoryPipelineResult,
    MemoryScenario,
    MemoryScenarioSearchHit,
    MemoryScenarioSearchResult,
    MemoryScope,
    MemoryScopeFilter,
    MemorySearchHit,
    MemorySearchRequest,
    MemorySearchResult,
)
from anchor.application.memory.provider_service import redact_sensitive_text
from anchor.application.provider_ports import MemoryExtractionProviderPort
from anchor.application.retrieval.document_chunking import count_tokens


class MemoryService:
    def __init__(self, repository: SqliteMemoryRepository, project: str, budget_tokens: int = 800) -> None:
        if budget_tokens <= 0:
            raise ValueError("budget_tokens must be greater than zero")
        self._repository = repository
        self._project = project
        self._budget_tokens = budget_tokens
        self._extraction_provider: MemoryExtractionProviderPort | None = None
        self._extraction_model = ""
        self._provider_name = "configured_memory_provider"
        self._external_send_allowed = False
        self._external_projects: set[str] = set()
        self._max_extracted_facts = 20

    def configure_extraction(
        self,
        provider: MemoryExtractionProviderPort | None,
        model: str = "",
        *,
        external_send_allowed: bool = False,
        external_projects: list[str] | None = None,
        provider_name: str = "configured_memory_provider",
        max_extracted_facts: int = 20,
    ) -> None:
        if max_extracted_facts <= 0:
            raise ValueError("max_extracted_facts must be greater than zero")
        self._extraction_provider = provider
        self._extraction_model = model
        self._provider_name = provider_name
        self._external_send_allowed = external_send_allowed
        self._external_projects = set(external_projects or [])
        self._max_extracted_facts = max_extracted_facts

    def preview_extraction(self, *, project: str | None = None, limit: int = 20) -> dict[str, object]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        resolved_project = project or self._project
        checkpoint = self._repository.get_checkpoint(project=resolved_project, chat_id=None)
        after_updated_at = checkpoint.get("last_history_updated_at") if checkpoint else None
        if not isinstance(after_updated_at, str):
            after_updated_at = None
        entries = self._repository.recent_history(
            project=resolved_project,
            after_updated_at=after_updated_at,
            limit=limit,
        )
        allowed = self._external_send_allowed and (
            "*" in self._external_projects
            or resolved_project in self._external_projects
        )
        return {
            "project": resolved_project,
            "allowed": allowed,
            "provider_configured": self._extraction_provider is not None and bool(self._extraction_model.strip()),
            "model": self._extraction_model,
            "count": len(entries),
            "evidence_refs": [entry["id"] for entry in entries],
            "entries": [
                {
                    "id": entry["id"],
                    "entry_type": entry["entry_type"],
                    "payload": redact_sensitive_text(entry["payload"]),
                }
                for entry in entries
            ],
        }

    def capture(
        self,
        *,
        content: str,
        fact_type: str,
        scope: MemoryScope = "project",
        project: str | None = None,
        chat_id: str | None = None,
        confidence: float = 1.0,
        evidence_refs: list[str | dict[str, object]] | None = None,
        status: MemoryFactStatus = "candidate",
        valid_from: str | None = None,
        valid_until: str | None = None,
        supersedes_id: str | None = None,
    ) -> MemoryFact:
        resolved_project = project or self._project
        refs = evidence_refs or []
        if status == "active" and not refs:
            raise ValueError("active memory facts require evidence_refs")
        if scope == "global" and not refs:
            raise ValueError("global memory facts require evidence_refs")
        candidate = MemoryFactCreate(
            scope=scope,
            project=resolved_project,
            source_chat_id=chat_id,
            fact_type=fact_type,
            content=content,
            confidence=confidence,
            status=status,
            evidence_refs=refs,
            valid_from=valid_from,
            valid_until=valid_until,
            supersedes_id=supersedes_id,
        )
        duplicate = self._repository.find_duplicate(candidate)
        if duplicate is not None and supersedes_id is None:
            merged = self._repository.merge_duplicate(
                duplicate.id,
                evidence_refs=refs,
                confidence=confidence,
                status=status,
            )
            if merged is None:
                raise LookupError(f"memory fact not found: {duplicate.id}")
            return merged
        return self._repository.create(candidate)

    def get(self, fact_id: str) -> MemoryFact:
        fact = self._repository.get(fact_id)
        if fact is None:
            raise LookupError(f"memory fact not found: {fact_id}")
        return fact

    def evidence(self, fact_id: str, *, project: str | None = None) -> MemoryEvidenceResult:
        fact = self.get(fact_id)
        resolved_project = project or self._project
        if fact.scope != "global" and fact.project != resolved_project:
            raise LookupError(f"memory fact not found: {fact_id}")
        if fact.scope == "global" and fact.project and fact.project != resolved_project:
            raise LookupError(f"memory evidence is outside project scope: {fact_id}")
        records = self._repository.get_evidence_records(fact.evidence_refs, project=resolved_project)
        return MemoryEvidenceResult(
            fact_id=fact.id,
            project=resolved_project,
            count=sum(1 for item in records if item["found"]),
            evidence=[MemoryEvidenceItem.model_validate(item) for item in records],
        )

    def search_scenarios(
        self,
        *,
        query: str,
        project: str | None = None,
        limit: int = 5,
    ) -> MemoryScenarioSearchResult:
        hits = self._repository.search_scenarios(query, projects=[project or self._project], limit=limit)
        return MemoryScenarioSearchResult(
            query=query,
            count=len(hits),
            results=[
                MemoryScenarioSearchHit(scenario=scenario, score=score, snippet=snippet)
                for scenario, score, snippet in hits
            ],
        )

    def conflicts(
        self,
        *,
        project: str | None = None,
        chat_id: str | None = None,
        limit: int = 20,
    ) -> MemoryConflictResult:
        groups = self._repository.active_conflicts(
            project=project or self._project,
            chat_id=chat_id,
            limit=limit,
        )
        return MemoryConflictResult(
            count=len(groups),
            groups=[
                MemoryConflictGroup(
                    scope=scope,
                    project=group_project,
                    chat_id=source_chat_id,
                    fact_type=fact_type,
                    facts=facts,
                )
                for scope, group_project, source_chat_id, fact_type, facts in groups
            ],
        )

    def metrics(self, *, project: str | None = None) -> MemoryMetricsResult:
        return MemoryMetricsResult.model_validate(self._repository.metrics(project=project or self._project))

    def promote(
        self,
        fact_id: str,
        *,
        scope: MemoryScope,
        project: str | None = None,
        chat_id: str | None = None,
        source_project: str | None = None,
    ) -> MemoryFact:
        resolved_source_project = source_project or self._project
        fact = self._repository.get(fact_id)
        if fact is None or fact.project != resolved_source_project:
            raise LookupError(f"memory fact not found in project {resolved_source_project}: {fact_id}")
        if fact.status in {"deleted", "superseded"}:
            raise ValueError(f"terminal memory fact cannot be promoted: {fact_id}")
        if not fact.evidence_refs:
            raise ValueError("memory fact promotion requires evidence_refs")
        # Global controls retrieval visibility; project remains the immutable
        # provenance/authorization boundary for later lifecycle mutations.
        if project is not None and project != resolved_source_project:
            raise ValueError("memory promotion cannot change source project")
        resolved_project = resolved_source_project
        if scope == "global" and (project is not None or chat_id is not None):
            raise ValueError("global promotion does not accept project or chat_id targets")
        resolved_chat = (
            (chat_id if chat_id is not None else fact.source_chat_id)
            if scope == "chat"
            else None
        )
        promoted = self._repository.update_scope(
            fact_id,
            scope=scope,
            project=resolved_project,
            source_chat_id=resolved_chat,
            source_project=resolved_source_project,
            expected_status=fact.status,
        )
        if promoted is None:
            raise LookupError(f"memory fact not found: {fact_id}")
        return promoted

    def update_status(
        self, fact_id: str, status: MemoryFactStatus, *, project: str | None = None
    ) -> MemoryFact:
        resolved_project = project or self._project
        current = self._repository.get(fact_id)
        if current is None or current.project != resolved_project:
            raise LookupError(f"memory fact not found in project {resolved_project}: {fact_id}")
        if current.status in {"deleted", "superseded"}:
            raise ValueError(f"terminal memory fact cannot change status: {fact_id}")
        if status == "active" and not current.evidence_refs:
            raise ValueError("active memory facts require evidence_refs")
        updated = self._repository.update_status(
            fact_id,
            status,
            source_project=resolved_project,
            expected_status=current.status,
        )
        if updated is None:
            raise LookupError(f"memory fact not found: {fact_id}")
        return updated

    def search(
        self,
        *,
        query: str,
        scope: MemoryScopeFilter = "all",
        project: str | None = None,
        projects: list[str] | None = None,
        chat_id: str | None = None,
        fact_type: str | None = None,
        status: MemoryFactStatus | list[MemoryFactStatus] | None = "active",
        limit: int = 20,
    ) -> MemorySearchResult:
        request = MemorySearchRequest(
            query=query,
            scope=scope,
            project=project,
            projects=projects,
            chat_id=chat_id,
            fact_type=fact_type,
            status=status,
            limit=limit,
        )
        resolved_projects = request.projects or ([request.project] if request.project else None)
        if request.scope == "all" and not resolved_projects and request.chat_id is None:
            resolved_projects = [self._project]
        statuses: list[MemoryFactStatus] = (
            [request.status]
            if isinstance(request.status, str)
            else request.status
            if isinstance(request.status, list)
            else ["active"]
        )
        hits = self._repository.search(
            request.query,
            scope=request.scope,
            projects=resolved_projects,
            chat_id=request.chat_id,
            fact_type=request.fact_type,
            statuses=statuses,
            limit=request.limit,
        )
        return MemorySearchResult(
            query=request.query,
            count=len(hits),
            results=[
                MemorySearchHit(fact=fact, score=score, snippet=snippet)
                for fact, score, snippet in hits
            ],
        )

    def recall(
        self,
        *,
        query: str,
        project: str | None = None,
        chat_id: str | None = None,
        limit: int = 5,
    ) -> MemorySearchResult:
        return self.search(
            query=query,
            scope="all",
            projects=[project or self._project],
            chat_id=chat_id,
            status="active",
            limit=limit,
        )

    def build_context(
        self,
        *,
        query: str,
        project: str | None = None,
        chat_id: str | None = None,
        limit: int = 5,
        budget_tokens: int | None = None,
    ) -> MemoryContextResult:
        resolved_project = project or self._project
        recalled = self.recall(query=query, project=resolved_project, chat_id=chat_id, limit=limit)
        scenario_result = self.search_scenarios(query=query, project=resolved_project, limit=limit)
        resolved_budget = budget_tokens if budget_tokens is not None else self._budget_tokens
        if resolved_budget <= 0:
            raise ValueError("budget_tokens must be greater than zero")
        lines = [
            "<anchor_memory>",
            f"Project: {resolved_project}",
            *( [f"Chat: {chat_id}"] if chat_id else [] ),
        ]
        selected: list[MemorySearchHit] = []
        selected_scenarios: list[MemoryScenario] = []
        current_tokens = count_tokens("\n".join([*lines, "</anchor_memory>"]))
        for scenario_hit in scenario_result.results:
            scenario = scenario_hit.scenario
            line = f"- [scenario/{scenario.scope}] {scenario.title}: {scenario.summary}"
            line_tokens = count_tokens(line)
            if current_tokens + line_tokens > resolved_budget:
                break
            lines.append(line)
            selected_scenarios.append(scenario)
            current_tokens += line_tokens
        for fact_hit in recalled.results:
            fact = fact_hit.fact
            scope = fact.scope if fact.scope != "project" else f"project:{fact.project}"
            line = f"- [{scope}/{fact.fact_type}] {fact.content}"
            line_tokens = count_tokens(line)
            if selected and current_tokens + line_tokens > resolved_budget:
                break
            if not selected and current_tokens + line_tokens > resolved_budget:
                remaining = resolved_budget - current_tokens
                line = self._truncate_to_tokens(line, remaining)
                if not line:
                    break
                line_tokens = count_tokens(line)
            lines.append(line)
            selected.append(fact_hit)
            current_tokens += line_tokens
        lines.append("</anchor_memory>")
        return MemoryContextResult(
            query=query,
            project=resolved_project,
            chat_id=chat_id,
            count=len(selected),
            scenario_count=len(selected_scenarios),
            budget_tokens=resolved_budget,
            context="\n".join(lines),
            scenarios=[scenario.model_dump() for scenario in selected_scenarios],
            results=selected,
        )

    @staticmethod
    def _truncate_to_tokens(text: str, budget_tokens: int) -> str:
        if budget_tokens <= 0:
            return ""
        if count_tokens(text) <= budget_tokens:
            return text
        low, high = 0, len(text)
        best = ""
        while low < high:
            middle = (low + high + 1) // 2
            candidate = text[:middle].rstrip()
            if count_tokens(candidate) <= budget_tokens:
                best = candidate
                low = middle
            else:
                high = middle - 1
        return best

    def invalidate_by_evidence(self, evidence_ids: list[str]) -> int:
        return self._repository.invalidate_by_evidence(evidence_ids)

    def extract(
        self,
        *,
        project: str | None = None,
        chat_id: str | None = None,
        limit: int = 20,
    ) -> MemoryPipelineResult:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        resolved_project = project or self._project
        checkpoint = self._repository.get_checkpoint(project=resolved_project, chat_id=chat_id)
        after_updated_at = checkpoint.get("last_history_updated_at") if checkpoint else None
        if not isinstance(after_updated_at, str):
            after_updated_at = None
        if not self._external_send_allowed or (
            "*" not in self._external_projects
            and resolved_project not in self._external_projects
        ):
            error = "external memory extraction is not allowed for this project"
            self._repository.save_checkpoint(
                project=resolved_project,
                chat_id=chat_id,
                last_history_updated_at=after_updated_at,
                processed_count=0,
                status="error",
                last_error=error,
            )
            raise RuntimeError(error)
        if self._extraction_provider is None or not self._extraction_model.strip():
            self._repository.save_checkpoint(
                project=resolved_project,
                chat_id=chat_id,
                last_history_updated_at=after_updated_at,
                processed_count=0,
                status="error",
                last_error="memory extraction provider is not configured",
            )
            raise RuntimeError("memory extraction provider is not configured")
        self._repository.save_checkpoint(
            project=resolved_project,
            chat_id=chat_id,
            last_history_updated_at=after_updated_at,
            processed_count=0,
            status="running",
        )
        try:
            entries = self._repository.recent_history(
                project=resolved_project,
                after_updated_at=after_updated_at,
                limit=limit,
            )
            if not entries:
                self._repository.save_checkpoint(
                    project=resolved_project,
                    chat_id=chat_id,
                    last_history_updated_at=after_updated_at,
                    processed_count=0,
                    status="completed",
                )
                return MemoryPipelineResult(
                    project=resolved_project,
                    chat_id=chat_id,
                    processed_history=0,
                    extracted_facts=0,
                    checkpoint_status="completed",
                )
            evidence_refs = [entry["id"] for entry in entries]
            redacted_entries: list[tuple[dict[str, str], str]] = []
            redacted_item_count = 0
            for entry in entries:
                redacted_payload = redact_sensitive_text(entry["payload"])
                if redacted_payload != entry["payload"]:
                    redacted_item_count += 1
                redacted_entries.append((entry, redacted_payload))
            audit_context = {
                "provider": self._provider_name,
                "model": self._extraction_model,
                "project": resolved_project,
                "scope": "chat" if chat_id else "project",
                "chat_id": chat_id,
                "batch_size": len(entries),
                "redacted_item_count": redacted_item_count,
            }
            transcript = "\n\n".join(
                f"[{entry['id']}] {entry['entry_type']}: {payload}"
                for entry, payload in redacted_entries
            )
            raw_facts = self._extraction_provider.extract_facts(transcript, evidence_refs, self._extraction_model)
            if len(raw_facts) > self._max_extracted_facts:
                raise ValueError("memory provider returned too many facts")
            candidate_facts: list[MemoryFact] = []
            seen_fact_ids: set[str] = set()
            for raw_fact in raw_facts:
                content = raw_fact.get("content")
                fact_type = raw_fact.get("fact_type", "fact")
                if not isinstance(content, str) or not content.strip() or not isinstance(fact_type, str):
                    continue
                raw_scope = raw_fact.get("scope", "project")
                if raw_scope not in {"project", "global"}:
                    continue
                scope: MemoryScope = raw_scope
                confidence = raw_fact.get("confidence", 0.5)
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                    continue
                normalized_evidence_refs: list[str | dict[str, object]] = list(evidence_refs)
                fact = self.capture(
                    content=content,
                    fact_type=fact_type,
                    scope=scope,
                    project=resolved_project,
                    chat_id=chat_id,
                    confidence=max(0.0, min(1.0, float(confidence))),
                    evidence_refs=normalized_evidence_refs,
                    status="candidate",
                )
                if fact.id not in seen_fact_ids:
                    candidate_facts.append(fact)
                    seen_fact_ids.add(fact.id)
            scenario = None
            if candidate_facts:
                payload = self._extraction_provider.summarize_scenario(
                    [fact.content for fact in candidate_facts], evidence_refs, self._extraction_model
                )
                title = payload.get("title") if isinstance(payload, dict) else None
                summary = payload.get("summary") if isinstance(payload, dict) else None
                if not isinstance(title, str) or not title.strip() or not isinstance(summary, str) or not summary.strip():
                    raise ValueError("scenario response must contain non-empty title and summary")
                scenario = self._repository.find_duplicate_scenario(
                    scope="project", project=resolved_project, evidence_refs=evidence_refs
                )
                if scenario is None:
                    scenario = self._repository.create_scenario(
                        scope="project",
                        project=resolved_project,
                        title=title.strip(),
                        summary=summary.strip(),
                        fact_ids=[fact.id for fact in candidate_facts],
                        evidence_refs=evidence_refs,
                    )
                for fact in candidate_facts:
                    if fact.status == "candidate":
                        self.update_status(fact.id, "active", project=resolved_project)
            self._repository.record_event(
                entity_type="memory_pipeline",
                entity_id=f"{resolved_project}\x00{chat_id or ''}",
                event_type="external_memory_extraction",
                payload={**audit_context, "outcome": "completed", "extracted_fact_count": len(candidate_facts)},
            )
            last_updated_at = entries[-1]["updated_at"]
            self._repository.save_checkpoint(
                project=resolved_project,
                chat_id=chat_id,
                last_history_updated_at=last_updated_at,
                processed_count=len(entries),
                status="completed",
            )
            return MemoryPipelineResult(
                project=resolved_project,
                chat_id=chat_id,
                processed_history=len(entries),
                extracted_facts=len(candidate_facts),
                scenario=scenario,
                checkpoint_status="completed",
            )
        except Exception as exc:
            public_error = f"memory extraction failed ({type(exc).__name__})"
            if "audit_context" in locals():
                self._repository.record_event(
                    entity_type="memory_pipeline",
                    entity_id=f"{resolved_project}\x00{chat_id or ''}",
                    event_type="external_memory_extraction",
                    payload={**audit_context, "outcome": "error", "error_type": type(exc).__name__},
                )
            self._repository.save_checkpoint(
                project=resolved_project,
                chat_id=chat_id,
                last_history_updated_at=after_updated_at,
                processed_count=0,
                status="error",
                last_error=public_error,
            )
            raise RuntimeError(public_error) from None
