from __future__ import annotations

import os

from openai import OpenAI

from anchor.application.provider_ports import EmbeddingsProviderPort


class OpenAICompatibleEmbeddingsProvider(EmbeddingsProviderPort):
    def __init__(self, base_url: str, api_key_env: str) -> None:
        self._base_url = base_url
        self._api_key_env = api_key_env

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        api_key = os.getenv(self._api_key_env, "EMPTY")
        client = OpenAI(base_url=self._base_url, api_key=api_key)
        response = client.embeddings.create(model=model, input=texts)
        return [list(item.embedding) for item in response.data]
