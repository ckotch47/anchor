from __future__ import annotations

import os

from openai import DefaultHttpxClient, OpenAI

from anchor.application.provider_ports import EmbeddingsProviderPort
from anchor.application.provider_security import raise_provider_error, validate_provider_endpoint


class OpenAICompatibleEmbeddingsProvider(EmbeddingsProviderPort):
    def __init__(self, base_url: str, api_key_env: str) -> None:
        endpoint = validate_provider_endpoint(base_url)
        self._base_url = endpoint.base_url
        self._api_key_env = api_key_env
        self.endpoint = endpoint
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=os.getenv(self._api_key_env, "EMPTY"),
            http_client=DefaultHttpxClient(follow_redirects=False),
        )

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(model=model, input=texts)
        except Exception as exc:
            raise_provider_error("embeddings", exc)
        return [list(item.embedding) for item in response.data]
