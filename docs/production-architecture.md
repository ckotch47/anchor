# Production Architecture

## Goal

Build Qatoria Anchor as a production-oriented local system for agents:

- one user, one local instance
- one SQLite database as the only source of truth
- one application core, multiple thin transports
- retrieval-ready from day one
- no server required for the primary workflow

## Architectural style

Anchor is a modular monolith.

- `main` only wires the application
- application services own use-cases
- adapters own external systems and SQLite access
- CLI is the primary transport
- MCP over `stdio` can be added later as another thin transport

## Bounded contexts

- `notes`
- `tasks`
- `history`
- `search/indexing`
- `config`
- `ops`
- `memory`

Each context should have its own service and its own table(s), not a single polymorphic blob.

`memory` is the retrieval/read model over notes, tasks, and history, not a separate source-of-truth table.

## Data ownership

Use a shared document spine plus domain tables.

- `documents`
  - canonical row for text, timestamps, source, and stable identifiers
  - shared by notes, tasks, and history
- `notes`
  - note-specific metadata and relationships
- `tasks`
  - task-specific state, priority, and lifecycle
- `history_entries`
  - append-only activity log / working history
- `document_tags`
  - filtering and coarse retrieval
- `document_links`
  - related context and graph traversal

Derived and operational tables:

- `document_chunks`
  - chunking for long text and retrieval candidates
- `chunk_embeddings`
  - vector representations for semantic search
- `index_states`
  - lifecycle for derived data
- `events`
  - audit trail
- `settings`
  - runtime and system settings
- `schema_migrations`
  - schema versioning and applied migrations

## Retrieval stack

Retrieval is hybrid and should exist from the first production slice.

1. Lexical candidate generation
   - FTS over canonical text and/or chunks
2. Vector candidate generation
   - `sqlite-vector` backed similarity search
3. Score fusion
   - merge lexical and vector candidates
4. Rerank
   - local rerank model through an OpenAI-compatible provider interface
5. Compact response
   - return only the small result set the agent needs

Fallback rules:

- if embeddings or rerank are unavailable, lexical retrieval still works
- if generation is required and the provider is offline, emit a machine-readable error
- search should degrade, not fail, when the provider is missing

## Provider strategy

- Embeddings and rerank are externalized behind an OpenAI-compatible client contract.
- Local endpoints are allowed and preferred for this project.
- The app should not depend on a remote server for the primary workflow.

## Non-goals

- microservices
- multi-user backend
- separate database per feature
- self-HTTP between internal modules
- one giant `items` table as the only long-term domain model

## Evolution path

- CLI remains stable
- MCP over `stdio` can be added later without changing the core use-cases
- future sync or replication layers must preserve the SQLite source of truth
