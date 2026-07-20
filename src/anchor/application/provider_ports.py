from __future__ import annotations

from typing import Any, Protocol


class EmbeddingsProviderPort(Protocol):
    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...


class RerankProviderPort(Protocol):
    def rerank(self, query: str, texts: list[str], model: str) -> list[float]: ...


class MemoryExtractionProviderPort(Protocol):
    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, Any]]: ...

    def summarize_scenario(self, facts: list[str], evidence_refs: list[str], model: str) -> dict[str, Any]: ...
