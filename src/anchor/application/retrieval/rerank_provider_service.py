from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from typing import Any

from openai import DefaultHttpxClient, OpenAI
from openai.types.chat import ChatCompletionMessageParam

from anchor.application.provider_ports import RerankProviderPort
from anchor.application.provider_security import raise_provider_error, validate_provider_endpoint


class NativeRerankProvider(RerankProviderPort):
    """Call a native rerank endpoint such as llama.cpp's /rerank."""

    def __init__(
        self,
        base_url: str,
        api_key_env: str,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        endpoint = validate_provider_endpoint(base_url)
        self._base_url = endpoint.base_url
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self._max_response_bytes = max_response_bytes
        self.endpoint = endpoint

    def rerank(self, query: str, texts: list[str], model: str) -> list[float]:
        payload = json.dumps({"model": model, "query": query, "documents": texts}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv(self._api_key_env, "").strip() if self._api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/rerank",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=self._timeout_seconds) as response:
                raw = response.read(self._max_response_bytes + 1)
                if len(raw) > self._max_response_bytes:
                    raise ValueError("native rerank response exceeds configured byte limit")
                decoded = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise_provider_error("native_rerank_http", exc)
        except urllib.error.URLError as exc:
            raise_provider_error("native_rerank_transport", exc)
        return self._parse_scores(decoded, len(texts))

    @classmethod
    def _parse_scores(cls, payload: Any, expected_count: int) -> list[float]:
        values: Any = payload
        if isinstance(payload, dict):
            values = payload.get("results", payload.get("scores", payload.get("data")))
        if isinstance(values, list) and values and isinstance(values[0], dict):
            indexed: list[float | None] = [None] * expected_count
            for item in values:
                index = item.get("index")
                score = item.get("relevance_score", item.get("score"))
                if (
                    isinstance(index, bool)
                    or not isinstance(index, int)
                    or not 0 <= index < expected_count
                    or indexed[index] is not None
                    or isinstance(score, bool)
                    or not isinstance(score, (int, float))
                ):
                    raise ValueError("native rerank response contains invalid indexes or scores")
                if not math.isfinite(float(score)):
                    raise ValueError("native rerank scores must be finite")
                indexed[index] = float(score)
            if any(score is None for score in indexed):
                raise ValueError("native rerank response indexes are incomplete")
            values = indexed
        if not isinstance(values, list) or len(values) != expected_count:
            raise ValueError("native rerank response must contain one score per document")
        scores: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("native rerank scores must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError("native rerank scores must be finite")
            scores.append(float(value))
        return scores


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleRerankProvider(RerankProviderPort):
    def __init__(self, base_url: str, api_key_env: str, max_response_bytes: int = 1_048_576) -> None:
        endpoint = validate_provider_endpoint(base_url)
        self._base_url = endpoint.base_url
        self._api_key_env = api_key_env
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self._max_response_bytes = max_response_bytes
        self.endpoint = endpoint
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=os.getenv(self._api_key_env, "EMPTY"),
            http_client=DefaultHttpxClient(follow_redirects=False),
        )

    def rerank(self, query: str, texts: list[str], model: str) -> list[float]:
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    "Return valid JSON only. "
                    "The JSON object must contain a key named 'scores' with a list of floats from 0 to 1. "
                    "The list must be in the same order as the provided documents."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(query, texts),
            },
        ]
        try:
            response = self._client.chat.completions.create(model=model, messages=messages, temperature=0)
        except Exception as exc:
            raise_provider_error("rerank", exc)
        content = response.choices[0].message.content or ""
        if len(content.encode("utf-8")) > self._max_response_bytes:
            raise ValueError("rerank response exceeds configured byte limit")
        return self._parse_scores(content, len(texts))

    @staticmethod
    def _build_prompt(query: str, texts: list[str]) -> str:
        lines = [f"Query: {query}", "Documents:"]
        for index, text in enumerate(texts, start=1):
            lines.append(f"{index}. {text}")
        return "\n".join(lines)

    def _parse_scores(self, content: str, expected_count: int) -> list[float]:
        payload = self._extract_json(content)
        scores = self._normalize_scores(payload, expected_count)
        if len(scores) != expected_count:
            raise ValueError("rerank response length does not match candidate count")
        return scores

    @staticmethod
    def _extract_json(content: str) -> Any:
        text = content.strip()
        if not text:
            raise ValueError("empty rerank response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = min([index for index in (text.find("{"), text.find("[")) if index >= 0], default=-1)
            end = max(text.rfind("}"), text.rfind("]"))
            if start < 0 or end < 0 or end <= start:
                raise ValueError("rerank response is not valid JSON")
            return json.loads(text[start : end + 1])

    @staticmethod
    def _normalize_scores(payload: Any, expected_count: int) -> list[float]:
        if isinstance(payload, dict):
            if "scores" in payload:
                values = payload["scores"]
            elif "rank" in payload:
                values = payload["rank"]
                if not isinstance(values, list) or len(values) != expected_count:
                    raise ValueError("rerank response rank field has invalid shape")
                return OpenAICompatibleRerankProvider._rank_to_scores(values)
            else:
                raise ValueError("rerank response missing scores field")
        else:
            values = payload
        if not isinstance(values, list):
            raise ValueError("rerank response scores must be a list")
        scores: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("rerank response scores must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError("rerank response scores must be finite")
            scores.append(float(value))
        return scores

    @staticmethod
    def _rank_to_scores(ranks: list[Any]) -> list[float]:
        numeric_ranks: list[float] = []
        for value in ranks:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("rerank response rank values must be numeric")
            if not math.isfinite(float(value)):
                raise ValueError("rerank response rank values must be finite")
            numeric_ranks.append(float(value))
        highest = max(numeric_ranks)
        lowest = min(numeric_ranks)
        if highest == lowest:
            return [1.0 for _ in numeric_ranks]
        return [1.0 - ((rank - lowest) / (highest - lowest)) for rank in numeric_ranks]
