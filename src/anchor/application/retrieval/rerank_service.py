from __future__ import annotations

from anchor.application.provider_ports import RerankProviderPort
from anchor.application.provider_security import ProviderEgressAuditPort, ProviderEgressPolicy


class RerankService:
    def __init__(
        self,
        provider: RerankProviderPort,
        model: str,
        *,
        egress_policy: ProviderEgressPolicy | None = None,
        audit_port: ProviderEgressAuditPort | None = None,
        max_batch_items: int = 100,
        max_batch_characters: int = 200_000,
    ) -> None:
        if max_batch_items <= 0 or max_batch_characters <= 0:
            raise ValueError("provider workload limits must be greater than zero")
        self._provider = provider
        self._model = model
        self._egress_policy = egress_policy
        self._audit_port = audit_port
        self._max_batch_items = max_batch_items
        self._max_batch_characters = max_batch_characters

    def rerank(self, query: str, texts: list[str], *, project: str | None = None) -> list[float]:
        if not texts:
            return []
        if len(texts) > self._max_batch_items:
            raise ValueError("rerank input exceeds configured item limit")
        if len(query) + sum(len(text) for text in texts) > self._max_batch_characters:
            raise ValueError("rerank input exceeds configured character limit")
        projects = [project] if project else []
        policy = self._egress_policy
        external = policy is not None and policy.endpoint.external
        if policy is not None:
            policy.authorize(projects)
        if external:
            self._record_audit(projects=projects, item_count=len(texts), outcome="attempt")
        try:
            scores = self._provider.rerank(query, texts, self._model)
        except Exception as exc:
            if external:
                self._record_audit(
                    projects=projects,
                    item_count=len(texts),
                    outcome="error",
                    error_type=type(exc).__name__,
                )
            raise
        if external:
            self._record_audit(projects=projects, item_count=len(texts), outcome="completed")
        if len(scores) != len(texts):
            raise ValueError("rerank provider returned unexpected number of scores")
        return scores

    def _record_audit(
        self,
        *,
        projects: list[str],
        item_count: int,
        outcome: str,
        error_type: str = "",
    ) -> None:
        if self._audit_port is None or self._egress_policy is None:
            raise RuntimeError("provider egress audit is not configured")
        self._audit_port.record(
            provider_kind="rerank",
            endpoint_host=self._egress_policy.endpoint.host,
            model=self._model,
            projects=projects,
            item_count=item_count,
            outcome=outcome,
            error_type=error_type,
        )
