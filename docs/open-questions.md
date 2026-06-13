# Open Questions and Decisions

Этот документ фиксирует, что уже решено, а что нужно отдельно добить до реализации.

## Already decided

- CLI contract must be stable for agents.
- Main goal is to reduce token burn through compact retrieval responses.
- Machine mode must return structured output.
- If external model/provider is unavailable, the tool should fall back to offline-only mode without generation.
- Agent-facing requests should support explicit per-command knobs for view, fields, limit, and budget.
- SQLite migrations should be forward-only, versioned, and protected by backup before upgrade.
- CLI startup should auto-apply pending migrations before command dispatch; `db migrate` remains the explicit repair/bootstrap command.
- Write sequencing should use WAL/busy_timeout/retry instead of introducing a server.
- Storage should stay file-based and simple.
- Derived indexes should have a lifecycle separate from source-of-truth records.
- Config should live in the user home folder as a single TOML file with optional profiles.
- Stable error codes should be documented and machine-readable.
- Tests and examples should be part of the plan from the start.
- Production architecture should use a shared document spine plus separate domain tables for notes, tasks, and history.
- Retrieval should include lexical search, vector search, embeddings, and rerank from the first production slice.

## Needs more design

- Exact default values for per-command limits and budgets.
- Which commands expose `full` view by default, if any.
- Packaging/distribution choice.

## Already decided for filesystem retrieval

- Use a dedicated `indexed_files` table plus `file_chunks` instead of stuffing path/language into `metatags`.
- Extend `documents.document_type` to include `file`.
- Use `vector.chunk_size` and `vector.chunk_overlap` for file chunking defaults.
- File chunking must be content-aware: Python `def`/`class`, Markdown `#` headings, fallback sliding window.
- `.gitignore`-aware filtering is mandatory, with fallback to filesystem metadata and `mtime` when git is unavailable.
- Binary files must be detected before read/chunking.
- Rename/delete must clean stale chunks and index rows.

## Current stance

- Prefer the smallest possible response that is still useful.
- Prefer retries and local persistence over introducing infrastructure.
- Prefer explicit configs and formats over implicit defaults when the agent needs control.
