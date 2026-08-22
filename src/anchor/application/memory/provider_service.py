from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import DefaultHttpxClient, OpenAI

from anchor.application.provider_ports import MemoryExtractionProviderPort
from anchor.application.provider_security import raise_provider_error, validate_provider_endpoint

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk-or-v1-|sk-)[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\b(?:bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)")


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    return _PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)


class OpenAICompatibleMemoryExtractionProvider(MemoryExtractionProviderPort):
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

    def extract_facts(self, text: str, evidence_refs: list[str], model: str) -> list[dict[str, Any]]:
        response = self._complete(
            model=model,
            system=(
                "Extract only durable, useful agent memory. Return JSON object "
                "with key 'facts', a list of objects containing fact_type, content, "
                "confidence, and scope. Scope must be project or global. Never invent "
                "evidence references; the caller will attach them."
            ),
            user=f"Evidence ids: {json.dumps(evidence_refs)}\nConversation:\n{redact_sensitive_text(text)}",
        )
        payload = self._parse_json(response)
        facts = payload.get("facts") if isinstance(payload, dict) else None
        if not isinstance(facts, list):
            raise ValueError("memory extraction response missing facts list")
        return [fact for fact in facts if isinstance(fact, dict)]

    def summarize_scenario(self, facts: list[str], evidence_refs: list[str], model: str) -> dict[str, Any]:
        response = self._complete(
            model=model,
            system=(
                "Group related agent memory facts into one concise scenario. Return JSON "
                "with title and summary strings. Do not add facts not present in input."
            ),
            user=f"Evidence ids: {json.dumps(evidence_refs)}\nFacts:\n"
            + "\n".join(redact_sensitive_text(fact) for fact in facts),
        )
        payload = self._parse_json(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("title"), str) or not isinstance(payload.get("summary"), str):
            raise ValueError("scenario response must contain title and summary")
        return payload

    def _complete(self, *, model: str, system: str, user: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise_provider_error("memory", exc)
        return response.choices[0].message.content or ""

    @staticmethod
    def _parse_json(content: str) -> Any:
        text = content.strip()
        if not text:
            raise ValueError("empty memory provider response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("memory provider response is not valid JSON") from exc
            return json.loads(text[start : end + 1])
