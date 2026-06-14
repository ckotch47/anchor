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
- `application/system` owns config, health, and migration services
- `application/<domain>` owns domain use-cases
- adapters own external systems and SQLite access
- CLI is the primary transport
- MCP over `stdio` is available as another thin transport via `anchor mcp` or `anchor-mcp`

## Bounded contexts

- `notes`
- `tasks`
- `history`
- `search/indexing`
- `filesystem/indexing`
- `config`
- `ops`
- `memory`

Each context should have its own service and its own table(s), not a single polymorphic blob.

`memory` is the retrieval/read model over notes, tasks, and history, not a separate source-of-truth table.

## Data ownership

Use a shared document spine plus domain tables.

- `documents`
  - canonical row for text, timestamps, source, stable identifiers, project scope, and metatags
  - shared by notes, tasks, and history
- `notes`
  - note-specific metadata, project scope, metatags, and relationships
- `tasks`
  - task-specific state, priority, lifecycle, direct task-link fields, project scope, and metatags
- `history_entries`
  - append-only activity log / working history, project scope, and metatags
- `document_tags`
  - filtering and coarse retrieval
- `document_links`
  - related context and graph traversal

Derived and operational tables:

- `document_chunks`
  - chunking for long text and retrieval candidates, carrying project scope for direct filtering
- `chunk_embeddings`
  - vector representations for semantic search, carrying project scope for direct filtering
- `index_states`
  - lifecycle for derived data
- `events`
  - audit trail
- `indexed_files`
  - live filesystem discovery, file metadata, language, root path, refresh state, and retrieval pointers without duplicating file contents
- `file_chunks`
  - retrieval chunks for indexed files when file length requires slicing
- `settings`
  - runtime and system settings
- `schema_migrations`
  - schema versioning and applied migrations

## Retrieval stack

Retrieval is hybrid and should exist from the first production slice.

1. Lexical candidate generation
   - FTS over canonical text and/or chunks
   - user query is normalized before `MATCH`
   - search is filtered by project and document type before ranking
   - metatags are filterable through indexed JSON keys or materialized search columns
2. Vector candidate generation
   - local scoring over stored chunk embeddings
   - SQLite vector extension is loaded on connection open and initializes `chunk_embeddings` for the configured dimension
3. Score fusion
   - explicit lexical/vector weighting, with lexical-only fallback when vector data is unavailable
4. Rerank
   - local rerank model through an OpenAI-compatible provider interface
   - rerank runs on the candidate pool before deduplication and trimming
5. Dedup and trim
   - keep one best chunk per document
   - trim the final response to the configured token budget
6. Compact response
   - return only the small result set the agent needs

Filesystem retrieval uses the same retrieval stack, but the source of truth is the live filesystem:

- index project roots on disk, not copied file snapshots
- provide `files get` for a full indexed-file record and `files list` for project-scoped navigation
- use `vector.chunk_size` and `vector.chunk_overlap` for file chunking defaults
- chunk files by content type: Python `def`/`class`, Markdown `#` headings, fallback sliding window by lines
- exclude binaries, vendor folders, build outputs, and configured ignore paths
- handle repositories without git by falling back to filesystem metadata and mtime
- clean stale chunks when files are removed or renamed
- materialize file chunk embeddings and rerank them through the same provider contract as notes
- store only metadata and retrieval slices in SQLite
- keep the file index incremental so refreshes are bounded

Fallback rules:

- if embeddings or rerank are unavailable, lexical retrieval still works
- if generation is required and the provider is offline, emit a machine-readable error
- search should degrade, not fail, when the provider is missing

## Provider strategy

- Embeddings and rerank are externalized behind an OpenAI-compatible client contract.
- Local endpoints are allowed and preferred for this project.
- The app should not depend on a remote server for the primary workflow.

## Project scope contract

- `project` and `metatags` are duplicated into every domain entity so list/search operations can scope locally without extra joins.
- `tasks` should support common task relationships directly, while `document_links` remains the richer graph for cross-entity references and follow-up context.
- `metatags` is stored as SQLite JSON text and treated as queryable metadata, not as PostgreSQL `jsonb`.
- Search should scope by `project` first, then document type, then any metatag filters, and only then run lexical/vector/rerank ranking.
- Filesystem retrieval should scope by project and root path before indexing, then apply ignore rules before any chunking or ranking.
- Cross-type retrieval should accept notes, tasks, history, and files as first-class search targets.

## Non-goals

- microservices
- multi-user backend
- separate database per feature
- self-HTTP between internal modules
- one giant `items` table as the only long-term domain model

## Evolution path

- CLI remains stable
- MCP over `stdio` stays a thin transport and does not change the core use-cases
- future sync or replication layers must preserve the SQLite source of truth
