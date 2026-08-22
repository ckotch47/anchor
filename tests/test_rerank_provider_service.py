from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from anchor.application.retrieval.rerank_provider_service import (
    NativeRerankProvider,
    OpenAICompatibleRerankProvider,
)


class NativeRerankProviderTest(unittest.TestCase):
    def test_parses_llama_cpp_response(self) -> None:
        provider = NativeRerankProvider("https://rerank.local", "API_KEY")
        response = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self, _limit=-1: json.dumps([
                {"index": 1, "relevance_score": 0.1},
                {"index": 0, "relevance_score": 0.9},
            ]).encode(),
        })()
        opener = type("Opener", (), {"open": lambda self, *_args, **_kwargs: response})()
        with patch(
            "anchor.application.retrieval.rerank_provider_service.urllib.request.build_opener",
            return_value=opener,
        ):
            self.assertEqual(provider.rerank("query", ["one", "two"], "bge"), [0.9, 0.1])

    def test_rejects_plaintext_remote_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            NativeRerankProvider("http://rerank.local", "")

    def test_rejects_oversized_native_response(self) -> None:
        provider = NativeRerankProvider(
            "http://127.0.0.1:8000/v1",
            "",
            max_response_bytes=8,
        )
        response = type(
            "Response",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
                "read": lambda self, _limit=-1: b"123456789",
            },
        )()
        opener = type("Opener", (), {"open": lambda self, *_args, **_kwargs: response})()

        with patch(
            "anchor.application.retrieval.rerank_provider_service.urllib.request.build_opener",
            return_value=opener,
        ), self.assertRaisesRegex(ValueError, "byte limit"):
            provider.rerank("query", ["one"], "bge")

    def test_rejects_wrong_score_count(self) -> None:
        with self.assertRaises(ValueError):
            NativeRerankProvider._parse_scores({"scores": [0.5]}, 2)

    def test_rejects_non_finite_scores_in_both_provider_formats(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            NativeRerankProvider._parse_scores({"scores": [float("nan"), 0.5]}, 2)
        with self.assertRaisesRegex(ValueError, "finite"):
            NativeRerankProvider._parse_scores(
                [{"index": 0, "score": float("inf")}, {"index": 1, "score": 0.5}],
                2,
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            OpenAICompatibleRerankProvider._normalize_scores(
                {"scores": [float("-inf"), 0.5]}, 2
            )
