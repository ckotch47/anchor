from __future__ import annotations

import json

from pydantic import BaseModel

from anchor.application.embedding_models import ChunkEmbeddingRecord
from anchor.application.provider_ports import EmbeddingsProviderPort


class ChunkEmbeddingsResult(BaseModel):
    model: str
    embeddings: list[ChunkEmbeddingRecord]


class EmbeddingService:
    def __init__(self, provider: EmbeddingsProviderPort, model: str) -> None:
        self._provider = provider
        self._model = model

    def embed_chunks(self, chunk_ids: list[str], texts: list[str]) -> ChunkEmbeddingsResult:
        vectors = self._provider.embed(texts=texts, model=self._model)
        embeddings = [
            ChunkEmbeddingRecord(chunk_id=chunk_id, model=self._model, embedding=vector)
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
        ]
        return ChunkEmbeddingsResult(model=self._model, embeddings=embeddings)

    @staticmethod
    def serialize_embedding(embedding: list[float]) -> str:
        return json.dumps(embedding, separators=(",", ":"))
