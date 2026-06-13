from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from anchor.application.retrieval.document_chunking import count_tokens

_PY_BOUNDARY_PATTERN = re.compile(r"^(?:async\s+def\s+|def\s+|class\s+)", re.MULTILINE)
_MD_HEADING_PATTERN = re.compile(r"^#{1,6}\s+", re.MULTILINE)


@dataclass(frozen=True)
class FileChunkDraft:
    chunk_index: int
    chunk_text: str
    token_count: int
    start_line: int
    end_line: int


class FileChunkingService:
    def chunk_file(
        self,
        *,
        path: Path,
        text: str,
        language: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[FileChunkDraft]:
        normalized = text.strip()
        if not normalized:
            return []
        if language == "python":
            return self._chunk_by_boundaries(text, _PY_BOUNDARY_PATTERN, chunk_size, chunk_overlap)
        if language in {"markdown", "md"}:
            return self._chunk_by_boundaries(text, _MD_HEADING_PATTERN, chunk_size, chunk_overlap)
        return self._chunk_sliding_window(text, chunk_size, chunk_overlap)

    def _chunk_by_boundaries(
        self,
        text: str,
        boundary_pattern: re.Pattern[str],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[FileChunkDraft]:
        lines = text.splitlines()
        segments: list[tuple[int, int]] = []
        start = 0
        for index, line in enumerate(lines):
            if index == 0:
                continue
            if boundary_pattern.match(line):
                segments.append((start, index))
                start = index
        segments.append((start, len(lines)))
        return self._pack_segments(lines, segments, chunk_size, chunk_overlap)

    def _chunk_sliding_window(self, text: str, chunk_size: int, chunk_overlap: int) -> list[FileChunkDraft]:
        lines = text.splitlines()
        segments = [(index, index + 1) for index in range(len(lines))]
        return self._pack_segments(lines, segments, chunk_size, chunk_overlap)

    def _pack_segments(
        self,
        lines: list[str],
        segments: list[tuple[int, int]],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[FileChunkDraft]:
        drafts: list[FileChunkDraft] = []
        chunk_lines: list[str] = []
        chunk_start = 0
        chunk_index = 0
        current_tokens = 0
        overlap_lines: list[str] = []
        overlap_tokens = 0
        for start, end in segments:
            segment_lines = lines[start:end]
            segment_text = "\n".join(segment_lines).strip()
            if not segment_text:
                continue
            segment_tokens = count_tokens(segment_text)
            if chunk_lines and current_tokens + segment_tokens > chunk_size:
                chunk_text = "\n".join(chunk_lines).strip()
                drafts.append(
                    FileChunkDraft(
                        chunk_index=chunk_index,
                        chunk_text=chunk_text,
                        token_count=max(1, count_tokens(chunk_text)),
                        start_line=chunk_start + 1,
                        end_line=chunk_start + len(chunk_lines),
                    )
                )
                chunk_index += 1
                overlap_lines, overlap_tokens = self._build_overlap(chunk_lines, chunk_overlap)
                chunk_lines = overlap_lines.copy()
                chunk_start = max(0, end - len(chunk_lines))
                current_tokens = overlap_tokens
            if not chunk_lines:
                chunk_start = start
            chunk_lines.extend(segment_lines)
            current_tokens += segment_tokens
        if chunk_lines:
            chunk_text = "\n".join(chunk_lines).strip()
            drafts.append(
                FileChunkDraft(
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    token_count=max(1, count_tokens(chunk_text)),
                    start_line=chunk_start + 1,
                    end_line=chunk_start + len(chunk_lines),
                )
            )
        return drafts

    def _build_overlap(self, chunk_lines: list[str], chunk_overlap: int) -> tuple[list[str], int]:
        if chunk_overlap <= 0:
            return [], 0
        overlap_lines: list[str] = []
        overlap_tokens = 0
        for line in reversed(chunk_lines):
            overlap_lines.insert(0, line)
            overlap_tokens += count_tokens(line)
            if overlap_tokens >= chunk_overlap:
                break
        return overlap_lines, overlap_tokens
