from __future__ import annotations

import math

from anchor.application.embeddings.service import EmbeddingService


class RerankService:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._embedding_service = embedding_service

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        query_embedding = self._embedding_service.embed_texts([query]).embeddings[0].embedding
        candidate_embeddings = self._embedding_service.embed_texts(texts).embeddings
        return [self._cosine_similarity(query_embedding, candidate.embedding) for candidate in candidate_embeddings]

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)
