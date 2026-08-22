from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from anchor.application.embeddings.service import EmbeddingService
from anchor.application.notes.service import NotesService
from anchor.application.retrieval.rerank_service import RerankService
from anchor.application.retrieval.search_query import SearchQuery


class RecordingEmbeddingsProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        del model
        self.calls.append(list(texts))
        return [[float(len(text))] for text in texts]


class RecordingRerankProvider:
    def __init__(self) -> None:
        self.calls = 0

    def rerank(self, query: str, texts: list[str], model: str) -> list[float]:
        del query, model
        self.calls += 1
        return [1.0 for _ in texts]


class ProviderWorkloadTest(unittest.TestCase):
    def test_embeddings_are_split_by_item_and_character_limits(self) -> None:
        provider = RecordingEmbeddingsProvider()
        service = EmbeddingService(
            provider=provider,
            model="embed",
            max_batch_items=2,
            max_batch_characters=5,
        )

        result = service.embed_texts(["aa", "bb", "ccc"])

        self.assertEqual(provider.calls, [["aa", "bb"], ["ccc"]])
        self.assertEqual(len(result.embeddings), 3)

    def test_oversized_embedding_item_is_rejected_before_provider_call(self) -> None:
        provider = RecordingEmbeddingsProvider()
        service = EmbeddingService(
            provider=provider,
            model="embed",
            max_batch_items=2,
            max_batch_characters=4,
        )

        with self.assertRaisesRegex(ValueError, "character limit"):
            service.embed_texts(["oversized"])

        self.assertEqual(provider.calls, [])

    def test_rerank_limits_fail_before_provider_call(self) -> None:
        provider = RecordingRerankProvider()
        service = RerankService(
            provider=provider,
            model="rerank",
            max_batch_items=2,
            max_batch_characters=8,
        )

        with self.assertRaisesRegex(ValueError, "item limit"):
            service.rerank("q", ["a", "b", "c"])
        with self.assertRaisesRegex(ValueError, "character limit"):
            service.rerank("query", ["long"])

        self.assertEqual(provider.calls, 0)

    def test_default_rerank_budget_accepts_normal_expanded_candidate_set(self) -> None:
        provider = RecordingRerankProvider()
        service = RerankService(provider=provider, model="rerank")

        scores = service.rerank("query", [f"candidate-{index}" for index in range(80)])

        self.assertEqual(len(scores), 80)
        self.assertEqual(provider.calls, 1)

    def test_hybrid_candidate_union_is_capped_before_rerank(self) -> None:
        provider = RecordingRerankProvider()
        service = NotesService(
            repository=Mock(),
            chunking_service=Mock(),
            project="repo-a",
            rerank_service=RerankService(provider=provider, model="rerank"),
        )
        lexical = [
            SimpleNamespace(
                chunk_id=f"lexical-{index}",
                lexical_score=1.0 - index / 100,
                vector_score=None,
                rerank_score=None,
                snippet=f"lexical {index}",
                token_count=2,
                note=SimpleNamespace(project="repo-a", title=f"Lexical {index}"),
            )
            for index in range(80)
        ]
        semantic = [
            SimpleNamespace(
                chunk_id=f"semantic-{index}",
                lexical_score=0.0,
                vector_score=1.0 - index / 100,
                rerank_score=None,
                snippet=f"semantic {index}",
                token_count=2,
                note=SimpleNamespace(project="repo-a", title=f"Semantic {index}"),
            )
            for index in range(80)
        ]
        with patch.object(service, "_search_lexical_candidates", return_value=lexical):
            with patch.object(service, "_search_vector_candidates", return_value=semantic):
                candidates = service._collect_candidates(
                    "deploy",
                    80,
                    "repo-a",
                    query_embedding=[1.0],
                )
        reranked = service._rerank_candidates("deploy", candidates)

        self.assertEqual(len(candidates), 80)
        self.assertEqual(len(reranked), 80)
        self.assertEqual(provider.calls, 1)

    def test_public_search_limits_are_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            SearchQuery(query="deploy", project="repo-a", limit=101)
        with self.assertRaises(ValidationError):
            SearchQuery(query="deploy", project="repo-a", budget_tokens=10_001)


if __name__ == "__main__":
    unittest.main()
