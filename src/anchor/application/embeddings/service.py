from __future__ import annotations

import json

from pydantic import BaseModel

from anchor.application.embeddings.models import ChunkEmbeddingRecord
from anchor.application.provider_ports import EmbeddingsProviderPort
from anchor.application.provider_security import ProviderEgressAuditPort, ProviderEgressPolicy


class ChunkEmbeddingsResult(BaseModel):
    model: str
    embeddings: list[ChunkEmbeddingRecord]


class EmbeddingService:
    def __init__(
        self,
        provider: EmbeddingsProviderPort,
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

    def embed_texts(self, texts: list[str], *, projects: list[str] | None = None) -> ChunkEmbeddingsResult:
        vectors = self._embed(texts, projects=projects or [])
        embeddings = [
            ChunkEmbeddingRecord(chunk_id=f"text_{index}", model=self._model, embedding=vector)
            for index, vector in enumerate(vectors)
        ]
        return ChunkEmbeddingsResult(model=self._model, embeddings=embeddings)

    def embed_chunks(
        self,
        chunk_ids: list[str],
        texts: list[str],
        *,
        project: str | None = None,
    ) -> ChunkEmbeddingsResult:
        vectors = self._embed(texts, projects=[project] if project else [])
        embeddings = [
            ChunkEmbeddingRecord(chunk_id=chunk_id, model=self._model, embedding=vector)
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
        ]
        return ChunkEmbeddingsResult(model=self._model, embeddings=embeddings)

    def _embed(self, texts: list[str], *, projects: list[str]) -> list[list[float]]:
        policy = self._egress_policy
        external = policy is not None and policy.endpoint.external
        if policy is not None:
            policy.authorize(projects)
        if external:
            self._record_audit(projects=projects, item_count=len(texts), outcome="attempt")
        try:
            vectors: list[list[float]] = []
            for batch in self._batches(texts):
                batch_vectors = self._provider.embed(texts=batch, model=self._model)
                if len(batch_vectors) != len(batch):
                    raise ValueError("embeddings provider returned unexpected number of vectors")
                vectors.extend(batch_vectors)
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
        return vectors

    def _batches(self, texts: list[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        batch: list[str] = []
        characters = 0
        for text in texts:
            text_characters = len(text)
            if text_characters > self._max_batch_characters:
                raise ValueError("embedding input exceeds configured character limit")
            if batch and (
                len(batch) >= self._max_batch_items
                or characters + text_characters > self._max_batch_characters
            ):
                batches.append(batch)
                batch = []
                characters = 0
            batch.append(text)
            characters += text_characters
        if batch:
            batches.append(batch)
        return batches

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
            provider_kind="embeddings",
            endpoint_host=self._egress_policy.endpoint.host,
            model=self._model,
            projects=projects,
            item_count=item_count,
            outcome=outcome,
            error_type=error_type,
        )

    @staticmethod
    def serialize_embedding(embedding: list[float]) -> str:
        return json.dumps(embedding, separators=(",", ":"))
