from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def normalize_fts5_query(raw_query: str) -> str:
    tokens = _TOKEN_PATTERN.findall(raw_query)
    if not tokens:
        raise ValueError("query must not be empty")
    return " AND ".join(tokens)
