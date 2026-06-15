from __future__ import annotations

import json
from collections.abc import Iterable

from anchor.application.links.models import DocumentLinkSummary


def parse_link_summaries(
    *raw_values: object,
    extras: Iterable[DocumentLinkSummary] | None = None,
) -> list[DocumentLinkSummary]:
    summaries: list[DocumentLinkSummary] = []
    for raw_value in raw_values:
        summaries.extend(_parse_raw_links(raw_value))
    if extras is not None:
        summaries.extend(extras)
    return _deduplicate_link_summaries(summaries)


def _parse_raw_links(raw_value: object) -> list[DocumentLinkSummary]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (bytes, bytearray)):
        raw_text = raw_value.decode("utf-8")
    elif isinstance(raw_value, str):
        raw_text = raw_value
    elif isinstance(raw_value, list):
        raw_items = raw_value
        return [_parse_link_summary(item) for item in raw_items if isinstance(item, dict)]
    else:
        return []
    if not raw_text.strip():
        return []
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [_parse_link_summary(item) for item in parsed if isinstance(item, dict)]


def _parse_link_summary(raw_item: dict[str, object]) -> DocumentLinkSummary:
    return DocumentLinkSummary(
        id=str(raw_item.get("id", "")),
        type=str(raw_item.get("type", "")),
        direction=str(raw_item.get("direction", "")),
    )


def _deduplicate_link_summaries(summaries: list[DocumentLinkSummary]) -> list[DocumentLinkSummary]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[DocumentLinkSummary] = []
    for summary in summaries:
        if not summary.id or not summary.type or not summary.direction:
            continue
        key = (summary.id, summary.type, summary.direction)
        if key in seen:
            continue
        seen.add(key)
        unique.append(summary)
    return unique
