# Implementation Plan

## Phase 1: Platform foundation

- create CLI entrypoint
- add config loader
- split system services into `application/system`
- add SQLite schema and migrations
- add JSON output contract
- add output budget rules for agent-facing commands
- add per-command request knobs and response envelope
- add schema version tracking and pre-migration backup
- make CLI startup apply pending migrations before dispatch
- add `health` and `db migrate`

## Phase 2: Domain surfaces

- implement `notes` as the first domain slice, then `tasks` and `history`
- add domain-specific tables for each context
- add shared `project` and `metatags` columns to every domain entity so all commands can scope and filter locally
- add shared `correlation_id` on the document spine for traceable agent activity
- add direct task-link fields for nesting and blocking as shortcuts, while keeping `document_links` as the general typed graph
- add generic `links` CLI/MCP commands for typed cross-entity relations
- add create/list/search/show/update flows
- add link support between documents
- add events/audit trail

## Phase 3: Retrieval engine

- add FTS search
- add explicit chunking/materialization pipeline for documents
- add query normalization before FTS `MATCH`
- add project-scoped retrieval and metatag filtering before ranking
- add embeddings generation on chunks through an OpenAI-compatible provider
- add vector retrieval with `sqlite-vector`
- add explicit score fusion strategy for lexical + vector candidates
- add rerank for top-k chunk candidates
- add dedup by document before returning results
- add budget trim before response emission
- add compact projection commands to avoid full-context responses
- add typed metatag schema validation and typed relation kinds in config

## Phase 4: Operations and resilience

- add export/import
- add backup/restore
- add reindex
- add WAL mode, busy_timeout, and lock retries
- add derived index state tracking
- add logs and metrics hooks

## Phase 5: Hardening

- add tests for CLI contract
- add migration tests
- add negative contract tests for empty payloads, invalid limits, and provider-offline paths
- add search quality checks
- add provider fallback behavior
- add documentation polish

## Phase 6: Filesystem retrieval

- add live filesystem indexing for project roots without copying file contents into the source-of-truth database
- add `indexed_files` and `file_chunks` tables, with `documents.document_type` extended to include `file`
- add file discovery rules for included/excluded paths, file size limits, and binary detection
- add `gitignore`-aware filtering, with fallback to filesystem metadata and mtime when git metadata is unavailable
- add clean-up on rename and delete so stale chunks do not survive removed files
- add incremental reindexing based on filesystem change tracking
- add content-aware file chunking: Python `def`/`class`, Markdown `#` headings, fallback sliding window with overlap
- wire file chunking to `vector.chunk_size` and `vector.chunk_overlap`
- add file/chunk retrieval commands with compact responses for agents
- add project-scoped search over indexed files, code, docs, notes, tasks, and history
- add embeddings and rerank for file search after the lexical file slice is stable
- add explicit config for roots, ignore patterns, and refresh policy
- add tests for index rebuild, change detection, and negative path handling

## Delivery order

1. Files retrieval hardening
   - live indexing
   - lexical search
   - vector embeddings
   - rerank
2. MCP stdio transport
   - typed tool schema over the same core use-cases
3. Index consolidation review
   - only if measured retrieval cost warrants schema simplification

## MCP parity backlog

- align MCP tools with CLI command-by-command instead of keeping a looser wrapper
- keep `CLI` as the source of truth and make `MCP` call the same application services
- normalize `compact/full` envelopes so `structuredContent` stays minimal by default
- mirror `notes`, `tasks`, `history`, `files`, `search`, `config`, `health`, and `db` contracts 1-1
- align shared arguments and defaults for `--project`, `--profile`, `--view`, `--limit`, `--cursor`, and `--budget-tokens`
- make MCP errors match CLI error codes and messages for invalid args, not found, and migration failures
- add parity tests that assert the same behavior through CLI and MCP for the same use-cases

### Suggested execution order

1. Envelope parity
2. Shared argument parity
3. CRUD and lookup parity per domain
4. Search parity
5. Error parity
6. Regression tests and docs sync
