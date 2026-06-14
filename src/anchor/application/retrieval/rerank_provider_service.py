from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from anchor.application.provider_ports import RerankProviderPort


class OpenAICompatibleRerankProvider(RerankProviderPort):
    def __init__(self, base_url: str, api_key_env: str) -> None:
        self._base_url = base_url
        self._api_key_env = api_key_env

    def rerank(self, query: str, texts: list[str], model: str) -> list[float]:
        api_key = os.getenv(self._api_key_env, "EMPTY")
        client = OpenAI(base_url=self._base_url, api_key=api_key)
        messages = [
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
        response = client.chat.completions.create(model=model, messages=messages, temperature=0)
        content = response.choices[0].message.content or ""
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
            scores.append(float(value))
        return scores

    @staticmethod
    def _rank_to_scores(ranks: list[Any]) -> list[float]:
        numeric_ranks: list[float] = []
        for value in ranks:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("rerank response rank values must be numeric")
            numeric_ranks.append(float(value))
        highest = max(numeric_ranks)
        lowest = min(numeric_ranks)
        if highest == lowest:
            return [1.0 for _ in numeric_ranks]
        return [1.0 - ((rank - lowest) / (highest - lowest)) for rank in numeric_ranks]
