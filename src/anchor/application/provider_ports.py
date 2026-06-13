from __future__ import annotations

from typing import Protocol


class EmbeddingsProviderPort(Protocol):
    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
