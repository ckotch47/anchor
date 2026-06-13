# Data Model

## Target schema

Anchor uses one SQLite database with a shared document spine and separate domain tables.

- `documents`
  - canonical row for text content, source, timestamps, and stable identity
  - shared by notes, tasks, and history
- `notes`
  - note-specific metadata and note lifecycle fields
  - 1:1 or 1:n with `documents`, depending on future note structure
- `tasks`
  - task-specific state, priority, due/completion fields
  - 1:1 with `documents`
- `history_entries`
  - append-only working history and activity trace
  - 1:1 with `documents`
- `document_tags`
  - filtering and coarse retrieval
- `document_links`
  - context graph for related records and agent follow-up

Derived and operational tables:

- `document_chunks`
  - chunking for long text and retrieval candidates
- `chunk_embeddings`
  - vector representations for semantic search
- `index_states`
  - lifecycle of derived data and reindex state
- `events`
  - audit trail of user and system actions
- `settings`
  - runtime and system settings
- `schema_migrations`
  - schema versioning and applied migration history

## Domain contract

- `documents.body` is the canonical text source.
- `notes`, `tasks`, and `history_entries` hold domain-specific state.
- `memory` is a read model over the domain tables, not a separate source of truth.
- Derived search data must be rebuildable from the canonical tables.

## Retrieval contract

- `document_chunks.chunk_text` is the unit for lexical and semantic retrieval.
- `chunk_embeddings.embedding` is derived and can be recomputed.
- `document_links` are used to pull neighboring context.
- `events` are append-only and never replace canonical rows.
- If vector or rerank data is stale or missing, lexical retrieval must still work.

## Indices

- FTS over canonical text and/or chunks.
- Index on document type/state/timestamps where applicable.
- Index on `document_links` source and target ids.
- Index on `schema_migrations.version`.
- Index on `index_states.state` and `index_states.index_type`.

## Storage norms

- Canonical rows and derived retrieval data are separate concerns.
- Search data can be rebuilt from `documents` + domain tables.
- Missing embeddings must degrade to text retrieval, not fail the command.
- Derived data lifecycle states: `pending`, `stale`, `ready`, `error`.

