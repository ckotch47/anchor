# Implementation Plan

## Phase 1: Platform foundation

- create CLI entrypoint
- add config loader
- add SQLite schema and migrations
- add JSON output contract
- add output budget rules for agent-facing commands
- add per-command request knobs and response envelope
- add schema version tracking and pre-migration backup
- make CLI startup apply pending migrations before dispatch
- add `health` and `db migrate`

## Phase 2: Domain surfaces

- implement `notes`, `tasks`, `history`
- add domain-specific tables for each context
- add create/list/search/show/update flows
- add link support between documents
- add events/audit trail

## Phase 3: Retrieval engine

- add FTS search
- add chunking for long content
- add embeddings generation
- add vector retrieval with `sqlite-vector`
- add rerank for top-k
- add compact projection commands to avoid full-context responses

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
