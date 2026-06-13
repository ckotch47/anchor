from __future__ import annotations


def combine_search_scores(
    *,
    lexical_score: float,
    vector_score: float | None = None,
    lexical_weight: float = 0.7,
    vector_weight: float = 0.3,
) -> float:
    if vector_score is None:
        return lexical_score
    return (lexical_weight * lexical_score) + (vector_weight * vector_score)
