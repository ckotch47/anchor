from __future__ import annotations

import unittest

from anchor.application.embeddings.provider_service import OpenAICompatibleEmbeddingsProvider
from anchor.application.memory.provider_service import OpenAICompatibleMemoryExtractionProvider
from anchor.application.provider_security import (
    ProviderEgressDenied,
    ProviderEgressPolicy,
    safe_provider_error,
    validate_provider_endpoint,
)
from anchor.application.retrieval.rerank_provider_service import OpenAICompatibleRerankProvider


class ProviderSecurityTest(unittest.TestCase):
    def test_loopback_http_is_local(self) -> None:
        for url in ("http://127.0.0.1:8000/v1", "http://[::1]:8000/v1", "http://localhost:8000/v1"):
            with self.subTest(url=url):
                endpoint = validate_provider_endpoint(url)
                self.assertFalse(endpoint.external)

    def test_external_endpoint_requires_https_and_clean_authority(self) -> None:
        for url in (
            "http://provider.example/v1",
            "https://user:secret@provider.example/v1",
            "https://provider.example/v1?token=secret",
            "file:///tmp/provider",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_provider_endpoint(url)

    def test_external_egress_is_default_deny_and_exact_project_scoped(self) -> None:
        endpoint = validate_provider_endpoint("https://provider.example/v1")
        with self.assertRaises(ProviderEgressDenied):
            ProviderEgressPolicy(endpoint=endpoint).authorize(["repo-a"])
        with self.assertRaises(ProviderEgressDenied):
            ProviderEgressPolicy(
                endpoint=endpoint,
                external_send_allowed=True,
                external_projects=("repo-a",),
            ).authorize(["repo-a", "repo-b"])

        ProviderEgressPolicy(
            endpoint=endpoint,
            external_send_allowed=True,
            external_projects=("repo-a", "repo-b"),
        ).authorize(["repo-a", "repo-b"])

    def test_provider_error_does_not_echo_exception_text(self) -> None:
        result = safe_provider_error("embedding", RuntimeError("token=SUPERSECRET"))

        self.assertEqual(result, "provider_error:embedding")
        self.assertNotIn("SUPERSECRET", result)

    def test_openai_compatible_clients_never_follow_redirects(self) -> None:
        providers = (
            OpenAICompatibleEmbeddingsProvider("https://provider.example/v1", "NO_KEY"),
            OpenAICompatibleMemoryExtractionProvider("https://provider.example/v1", "NO_KEY"),
            OpenAICompatibleRerankProvider("https://provider.example/v1", "NO_KEY"),
        )
        try:
            for provider in providers:
                with self.subTest(provider=type(provider).__name__):
                    self.assertFalse(provider._client._client.follow_redirects)
        finally:
            for provider in providers:
                provider._client.close()


if __name__ == "__main__":
    unittest.main()
