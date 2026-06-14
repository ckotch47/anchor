from __future__ import annotations

from anchor.application.provider_ports import RerankProviderPort


class RerankService:
    def __init__(self, provider: RerankProviderPort, model: str) -> None:
        self._provider = provider
        self._model = model

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = self._provider.rerank(query, texts, self._model)
        if len(scores) != len(texts):
            raise ValueError("rerank provider returned unexpected number of scores")
        return scores
