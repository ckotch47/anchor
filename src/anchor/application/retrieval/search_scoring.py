from __future__ import annotations


def combine_search_scores(
    *,
    lexical_score: float,
    vector_score: float | None = None,
    rerank_score: float | None = None,
    lexical_weight: float = 0.7,
    vector_weight: float = 0.3,
    rerank_weight: float = 0.8,
) -> float:
    if rerank_score is not None:
        score = rerank_weight * rerank_score
        if vector_score is not None:
            score += (1.0 - rerank_weight) * vector_score
        return score
    if vector_score is None:
        return lexical_score
    return (lexical_weight * lexical_score) + (vector_weight * vector_score)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)
