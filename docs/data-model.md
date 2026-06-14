# Data Model

## Target schema

Anchor uses one SQLite database with a shared document spine and separate domain tables.

## Domain tables

- `documents`
  - `id`
  - `project`
  - `metatags`
  - `correlation_id`
  - `document_type`
  - `title`
  - `body`
  - `source`
  - `source_ref`
  - `created_at`
  - `updated_at`
  - `deleted_at`
- `notes`
  - `document_id`
  - `project`
  - `metatags`
  - `correlation_id`
  - `note_kind`
  - `pinned`
  - `archived_at`
- `tasks`
  - `document_id`
  - `project`
  - `metatags`
  - `correlation_id`
  - `task_kind`
  - `status`
  - `priority`
  - `due_at`
  - `started_at`
  - `completed_at`
  - `blocked_reason`
  - `parent_document_id`
  - `blocked_by_document_id`
- `history_entries`
  - `document_id`
  - `project`
  - `metatags`
  - `entry_type`
  - `actor`
  - `payload`
  - `correlation_id`
- `document_tags`
  - filtering and coarse retrieval
- `document_links`
  - typed context graph for related records and agent follow-up

Derived and operational tables:

- `document_chunks`
  - chunking for long text and retrieval candidates, carrying project scope for direct filtering
- `chunk_embeddings`
  - vector representations for semantic search, carrying project scope for direct filtering
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
- `project` is duplicated on `documents`, `notes`, `tasks`, and `history_entries` so scoping never depends on join-time inference.
- `metatags` is duplicated on `documents`, `notes`, `tasks`, and `history_entries` as SQLite JSON text, not PostgreSQL `jsonb`.
- `correlation_id` is stored on the shared `documents` spine and on `history_entries` so agent activity can be traced across operations.
- `notes`, `tasks`, and `history_entries` hold domain-specific state.
- `tasks` support one-parent nesting and one-primary-blocker references directly, while `document_links` remains the general graph for richer cross-entity relations.
- `document_links.link_type` is the typed relation discriminator for the graph layer.
- `memory` is a read model over the domain tables, not a separate source of truth.
- Derived search data must be rebuildable from the canonical tables.
- Primary ids and opaque reference ids are UUIDv7 strings: entity ids, chunk ids, `parent_document_id`, `blocked_by_document_id`, and `correlation_id`.

## Retrieval contract

- `document_chunks.chunk_text` is the unit for lexical and semantic retrieval.
- `chunk_embeddings.embedding` is derived and can be recomputed.
- `document_links` are used to pull neighboring context.
- `events` are append-only and never replace canonical rows.
- Retrieval should scope by `project` before ranking and may filter on `metatags` as a first-class predicate.
- `metatags` search should rely on explicit indexed keys and/or JSON1 materialization, not unindexed blob scans.
- If vector or rerank data is stale or missing, lexical retrieval must still work.

## Indices

- FTS over canonical text and/or chunks.
- Index on project, document type/state, and timestamps where applicable.
- Index on common `metatags` keys where they are used for search or filtering.
- Index on `document_links` source and target ids.
- Index on `schema_migrations.version`.
- Index on `index_states.state` and `index_states.index_type`.

## Storage norms

- Canonical rows and derived retrieval data are separate concerns.
- Search and list queries should not need to infer project scope from source paths or ad hoc metadata.
- JSON metatags are stored as text in SQLite and treated as queryable metadata only where explicitly indexed.
- Search data can be rebuilt from `documents` + domain tables.
- Missing embeddings must degrade to text retrieval, not fail the command.
- Derived data lifecycle states: `pending`, `stale`, `ready`, `error`.
