# CLI Contract

## Правила

- Команды должны быть неинтерактивными по умолчанию.
- Machine mode возвращает JSON в stdout.
- Ошибки и debug-логи идут в stderr.
- Выходные коды стабильны и задокументированы.

## Request format

- Base shape: `anchor <domain> <action> [flags]`.
- Core flags:
  - `--format json`
  - `--view compact|full`
  - `--fields field1,field2,field3`
  - `--limit N`
  - `--budget tokens|bytes`
  - `--profile <name>`
- Command-specific flags can narrow the request further, but they must not break the shared envelope.
- If a command does not need a knob, it should ignore it rather than failing.

## Negative request contract

- Write and update commands such as `notes add`, `notes update`, `tasks add`, `tasks update`, and `history append` must reject empty payloads with `INVALID_ARGS`.
- Future search commands must reject invalid `--limit` values with `INVALID_ARGS` instead of silently clamping.
- If a command requires generation and the provider is unavailable, it must emit `OFFLINE_ONLY` or `PROVIDER_OFFLINE` with a stable JSON error envelope.

## Response format

- Success envelope:
```json
{
  "ok": true,
  "command": "memory.search",
  "data": {},
  "meta": {
    "duration_ms": 38,
    "db": "sqlite",
    "view": "compact"
  }
}
```
- Error envelope:
```json
{
  "ok": false,
  "command": "memory.search",
  "error": {
    "code": "DB_LOCKED",
    "message": "database is locked",
    "retryable": true
  },
  "meta": {
    "duration_ms": 5
  }
}
```
- `data` must contain the command result only.
- `meta` is for execution details, not business state.
- Retrieval commands should stay compact by default; `--view` is a request hint that is echoed in `meta` for compatibility with agent clients.
- For `list` and `search`, `compact` returns the minimal agent payload and `full` expands the underlying domain records when the slice supports it.
- For entity `get` and `search`, each returned item may include a compact `links` summary with `{id, type, direction}` entries so the agent can inspect nearby graph context without a second tool call.

## Per-command config

- Global config controls:
  - default provider/base URL,
  - default view,
  - default limits and budgets,
  - retry behavior,
  - offline-only fallback.
- Command-level flags override config for a single invocation.
- The implementation should prefer explicit overrides to hidden magic.

## Config commands

- `anchor config get [--profile <name>]`
- `anchor config set --section <runtime|provider|vector|profiles> --key <field> --value <raw> [--profile <name>]`
- `anchor config init [--force]`
- `config get` returns the full effective config plus the resolved config path.
- `config set` writes the updated config back to the user-folder TOML file.
- `config init` bootstraps the user config from `config.example.toml`.

## Current commands

### `anchor health`

- Describes whether the local core is ready and which config/profile was resolved.
- Useful as the first machine check before any agent workflow.
- If the maintenance window is due, `health` may also trigger scheduled SQLite cleanup from the `settings` table.

Example:

```bash
anchor health
```

### `anchor config get`

- Returns the effective runtime/provider/vector config for the selected profile.
- Use this when an agent needs to confirm provider URL, model names, or defaults.

Example:

```bash
anchor config get --profile full
```

### `anchor config set`

- Writes a single config field back to the user TOML file.
- Use this for per-user tuning of defaults, provider settings, or vector settings.

Example:

```bash
anchor config set --section runtime --key default_view --value full
```

### `anchor db migrate`

- Creates or updates the local SQLite schema.
- Runs automatically on CLI start, but stays available as an explicit bootstrap/repair command.

Example:

```bash
anchor db migrate
```

### `anchor db compact`

- Purges soft-deleted rows past a retention window, rebuilds FTS indexes, optionally vacuums the database, and truncates the WAL.
- Use this when the local SQLite file starts to accumulate tombstones, FTS fragmentation, or WAL growth.

Example:

```bash
anchor db compact --retention-days 30 --rebuild-search-indexes --vacuum --checkpoint
```

### `anchor notes add`

- Creates a note in the shared SQLite core.
- Requires `--title` and `--body`.
- Accepts `--project` to scope the note explicitly and `--metatags` as a JSON object string.
- Stores the note through the shared document spine, not a separate memory database.

Example:

```bash
anchor notes add --title "RAG plan" --body "Use SQLite FTS + vector + rerank" --project repo-a --metatags '{"topic":"rag"}'
```

### `anchor notes update`

- Partially updates a note in the shared SQLite core.
- Use `--id` with the note id returned by `notes add` or `notes list`.
- Accepts optional `--title`, `--body`, `--source`, `--source-ref`, `--pinned/--no-pinned`, `--project`, and `--metatags`.
- Leaves unspecified fields unchanged.
- Uses the selected project only as the lookup scope.

Example:

```bash
anchor notes update --id <note-id> --title "RAG plan v2" --project repo-a
```

### `anchor notes delete`

- Soft-deletes a note in the shared SQLite core.
- Use `--id` with the note id returned by `notes add` or `notes list`.
- Use `--project` to delete from a non-default project scope.
- The deleted note is removed from list/search/get visibility and its retrieval chunks are purged.

Example:

```bash
anchor notes delete --id <note-id> --project repo-a
```

### `anchor notes list`

- Returns the newest notes first.
- Emits a compact navigation record per note by default; `--view full` expands each item to the full note record.
- The target contract is project-scoped, so list/search should stay inside the selected project boundary.
- Use `--project` to override the default project scope from config.
- Use `--limit` to narrow the response.
- Use `--cursor` with the opaque `next_cursor` token to fetch the next page.

Example:

```bash
anchor notes list --limit 5 --cursor <next-cursor> --project repo-a
```

### `anchor notes get`

- Returns one note by its document id.
- Use `--id` with the value returned by `notes add` or `notes list`.
- Use `--project` to fetch from a non-default project scope.

Example:

```bash
anchor notes get --id <note-id> --project repo-a
```

### `anchor notes search`

- Searches note titles and bodies through the shared SQLite retrieval layer.
- Uses FTS over materialized retrieval chunks and vector reranking through SQLite-native vector search.
- On startup, the SQLite vector extension is loaded and the embeddings table is initialized for the configured dimension.
- Chunking stays a separate preprocessing step before retrieval and rerank.
- The search pipeline is lexical candidate generation, vector candidate generation, rerank, dedup by note, and budget trim.
- The final response is capped by the configured token budget so agents get a compact result set.
- `--view full` expands each hit to the full note record, while the default stays compact.
- In compact view, the response omits the echoed `query` field and keeps only the minimal hit envelope.
- If embeddings or rerank are unavailable, search degrades to lexical-only instead of failing.
- Search text is normalized before `MATCH`, so special FTS characters are treated as query text, not syntax.
- The target contract is project-scoped and can further filter by metatags before ranking.
- Search is filtered to the note domain before ranking.
- Each hit returns a compact note summary with `id`, `project`, `title`, `pinned`, `created_at`, `chunk_id`, `score`, and `snippet`.
- Use `--project` to search a specific repository or workspace.
- Start with `--limit` only when you need to trim the response.

Example:

```bash
anchor notes search --query "rag plan" --limit 5 --project repo-a
```

### `anchor history append`

- Appends a compact working-history entry to the shared SQLite core.
- Requires `--entry-type` and `--payload`.
- Accepts `--actor`, `--correlation-id`, `--project`, and `--metatags`.
- If `--correlation-id` is omitted, Anchor generates a UUIDv7 opaque id for the history entry.
- Uses the same document spine and retrieval indexing as the other domain slices.

Example:

```bash
anchor history append --entry-type deploy --payload "Deploy step completed" --project repo-a --metatags '{"topic":"ops"}'
```

### `anchor history search`

- Searches history entries through the shared retrieval layer.
- Uses the same lexical/vector/rerank/budget pipeline as notes, with vector search executed inside SQLite when the extension is available.
- Vector table initialization happens on connection open, so the search path does not depend on a separate service.
- Is project-scoped and returns compact hits with only `id`, `project`, `entry_type`, `actor`, `correlation_id`, `created_at`, and `snippet`.
- `--view full` expands each hit to the full history record.

Example:

```bash
anchor history search --query "deploy" --project repo-a
```

### `anchor history update`

- Partially updates a history entry in the shared SQLite core.
- Use `--id` with the history id returned by `history append`.
- Accepts optional `--entry-type`, `--payload`, `--actor`, `--correlation-id`, `--project`, and `--metatags`.
- Leaves unspecified fields unchanged and refreshes retrieval chunks when the textual payload changes.

Example:

```bash
anchor history update --id <history-id> --payload "Deploy step updated" --project repo-a
```

### `anchor history delete`

- Soft-deletes a history entry in the shared SQLite core.
- Use `--id` with the history id returned by `history append`.
- Use `--project` to delete from a non-default project scope.
- The deleted entry is removed from list/search/get visibility and its retrieval chunks are purged.

Example:

```bash
anchor history delete --id <history-id> --project repo-a
```

### `anchor links add`

- Creates a typed link between two document ids.
- `--relation-type` must be one of the configured relation kinds.
- Use this for task-to-note, note-to-history, file-to-task, and other typed graph edges.

Example:

```bash
anchor links add --source-id <task-id> --target-id <note-id> --relation-type references
```

### `anchor links list`

- Lists links by `--source-id` or `--target-id`.
- Provide one anchor id to inspect the outgoing or incoming graph neighborhood.

Example:

```bash
anchor links list --source-id <task-id>
```

### `anchor links delete`

- Deletes a typed link by source, target, and relation type.

Example:

```bash
anchor links delete --source-id <task-id> --target-id <note-id> --relation-type references
```

### `anchor tasks add`

- Creates a task in the shared SQLite core.
- Requires `--title`.
- Accepts `--body`, `--priority`, `--due-at`, `--task-kind`, `--project`, `--metatags`, `--parent-id`, and `--blocked-by-id`.
- `--parent-id` and `--blocked-by-id`, when provided, must be UUIDv7 values.
- Stores the task through the shared document spine, not a separate tracker database.

Example:

```bash
anchor tasks add --title "Ship tasks slice" --body "Implement tasks commands" --priority 2 --project repo-a --metatags '{"topic":"tasks"}'
```

### `anchor tasks search`

- Searches task titles and task bodies through the shared SQLite retrieval layer.
- Uses FTS over materialized task chunks.
- The search pipeline is lexical candidate generation plus compact hits with snippets; vector search remains reserved for the shared retrieval surface.
- Existing tasks without chunks are backfilled on demand before search so legacy rows stay searchable.
- Search text is normalized before `MATCH`, so special FTS characters are treated as query text, not syntax.
- The target contract is project-scoped and filtered to the task domain before ranking.
- If a provider is unavailable, task search stays lexical-only.
- In compact view, the response omits the echoed `query` field and keeps only the minimal hit envelope.

Example:

```bash
anchor tasks search --query "deploy" --limit 5 --project repo-a
```

### `anchor search`

- Searches across multiple domain slices in one request.
- Use `--types notes,tasks,files` to scope the retrieval surface explicitly.
- Cross-project search is opt-in through `--projects repo-a,repo-b`; the default remains a single selected project.
- The request is modeled as a first-class search query with `query`, `types`, `project`, optional `projects`, `limit`, `budget_tokens`, optional `weights`, and an opaque `--cursor` token for score-based pagination.
- The result envelope stays compact, can add explain-style retrieval stats with `--explain`, and returns `next_cursor` when another page is available.
- In compact view, the response omits the echoed query object and per-hit attributes; `--view full` restores the full search envelope.
- Current support covers `notes`, `tasks`, and `files`; `history` is reserved for the later slice.

Example:

```bash
anchor search --query "deploy" --types notes,tasks,files --limit 5 --project repo-a --projects repo-a,repo-b --cursor <next-cursor> --explain
```

### `anchor mcp`

- Starts the same core use-cases over MCP `stdio`.
- Exposes typed tools for health, config, notes, tasks, files, and cross-entity search.
- Uses the same SQLite container and service layer as the CLI.
- Mirrors the CLI `--view compact|full` contract on list and search tools so MCP agents can choose token-light or expanded payloads without a transport-specific shape.
- The same transport is also available as the `anchor-mcp` console script for direct stdio execution.

Example:

```bash
anchor mcp
```

### `anchor files index`

- Indexes live filesystem roots into `indexed_files` and `file_chunks`.
- Uses `--root` to point at one or more project roots.
- Applies `.gitignore`-aware filtering, binary detection, and `chunk_size` / `chunk_overlap` from config.
- Keeps the filesystem as the source of truth and stores only retrieval metadata in SQLite.

Example:

```bash
anchor files index --root ./repo --project repo-a
```

### `anchor files get`

- Returns the full indexed file record for one file by `--id` or `--path`.
- Use `--project` to scope the lookup to a repository or workspace.
- `--root`, `--language`, and `--path-prefix` narrow the lookup when agents know the file slice they want.
- Relative `--path` and `--path-prefix` values resolve against `--root` when it is provided, otherwise against the current working directory.
- `--view` is accepted for transport parity, but the command always returns the full file record.

Example:

```bash
anchor files get --path ./repo/app.py --project repo-a
```

### `anchor files delete`

- Soft-deletes one indexed file by `--id` or `--path`.
- Uses the same scoping rules as `files get`, including `--project`, `--root`, `--language`, and `--path-prefix`.
- Removes the file from future list/search/get visibility and clears its retrieval chunks.

Example:

```bash
anchor files delete --path ./repo/app.py --project repo-a
```

### `anchor files list`

- Returns indexed files for the selected project.
- Emits a compact navigation record by default; `--view full` expands each row to the full indexed file record.
- Use `--limit` to keep each page small when the repository is large.
- Use `--cursor` with the opaque UUIDv7-based token returned as `next_cursor` to fetch the next page.
- `--root`, `--language`, and `--path-prefix` narrow the list before pagination.
- The repository applies those filters in SQLite before rows are materialized, and pagination is driven by `document_id` instead of keeping the whole path list in memory.

Example:

```bash
anchor files list --limit 10 --cursor <next-cursor> --project repo-a
```

### `anchor files search`

- Searches indexed files through the same compact retrieval surface as notes and tasks.
- Returns file path, root path, language, file size, a snippet, and a compact score.
- Uses SQLite-native vector search when the extension is available.
- The vector layer is initialized from the shared connection lifecycle, not a separate index daemon.
- Uses the configured project scope by default.
- `--root`, `--language`, and `--path-prefix` narrow the candidate pool before rerank and budget trim.
- Relative `--path` and `--path-prefix` values resolve against `--root` when it is provided, otherwise against the current working directory.
- `--explain` adds retrieval stats to the machine response so agents can see candidate and dedup counts.
- In compact view, the response omits the echoed `query` field and any extra search metadata unless `--explain` is set.
- `--view full` expands each hit to the full indexed file record.

Example:

```bash
anchor files search --query "greet" --project repo-a
```

### `anchor tasks update`

- Partially updates a task in the shared SQLite core.
- Use `--id` with the task id returned by `tasks add` or `tasks list`.
- Accepts optional `--title`, `--body`, `--source`, `--source-ref`, `--priority`, `--due-at`, `--task-kind`, `--parent-id`, `--blocked-by-id`, `--project`, and `--metatags`.
- Leaves unspecified fields unchanged.
- Uses the selected project only as the lookup scope.

Example:

```bash
anchor tasks update --id <task-id> --priority 5 --project repo-a
```

### `anchor tasks list`

- Returns the newest tasks first.
- Emits a compact navigation record per task by default; `--view full` expands each item to the full task record.
- The target contract is project-scoped, so list/search should stay inside the selected project boundary.
- Use `--project` to override the default project scope from config.
- Use `--limit` to narrow the response.
- Use `--cursor` with the opaque `next_cursor` token to fetch the next page.
- `--view full` expands each task row to the full task record.

Example:

```bash
anchor tasks list --limit 5 --cursor <next-cursor> --project repo-a
```

### `anchor tasks done`

- Marks a task as completed.
- Use `--id` with the value returned by `tasks add` or `tasks list`.
- Use `--project` to complete a task in a non-default project scope.

Example:

```bash
anchor tasks done --id <task-id> --project repo-a
```

### `anchor tasks delete`

- Soft-deletes a task in the shared SQLite core.
- Use `--id` with the task id returned by `tasks add` or `tasks list`.
- Use `--project` to delete from a non-default project scope.
- The deleted task is removed from list/search/get visibility and its retrieval chunk is purged.

Example:

```bash
anchor tasks delete --id <task-id> --project repo-a
```

## Target command set

- `anchor memory capture`
- `anchor memory search`
- `anchor memory recall`
- `anchor notes add`
- `anchor notes update`
- `anchor notes search`
- `anchor tasks add`
- `anchor tasks search`
- `anchor tasks update`
- `anchor tasks list`
- `anchor tasks done`
- `anchor files index`
- `anchor files get`
- `anchor files delete`
- `anchor files list`
- `anchor files search`
- `anchor mcp`
- `anchor history append`
- `anchor history update`
- `anchor history delete`
- `anchor history search`
- `anchor db migrate`
- `anchor db reindex`
- CLI startup applies pending SQLite migrations before command dispatch.
- `db migrate` creates or updates the local SQLite database at `~/.qatoria/anchor/anchor.sqlite3`.
- `anchor backup export`
- `anchor backup import`
- `anchor health`
- `anchor config get`
- `anchor config set`

## Future command pattern

- `memory` is the unified retrieval surface over notes/tasks/history, not a separate source of truth.
- `notes` already reuses the shared retrieval-ready SQLite core.
- `files` adds live filesystem indexing on top of the same retrieval core.
- `history` and `tasks` reuse the same core for their current slices and future extensions.
- Each domain owns its table(s), while search uses shared document spine + derived retrieval tables.
- `project` and `metatags` are part of the target contract for all domain entities and should be respected by list/search commands.
- Mutable domain entities should expose partial `update` commands with the same project-scoped contract.
- Semantic vector retrieval and rerank are first-class layers on top of that core, not a separate database.

## Пример JSON ответа

```json
{
  "ok": true,
  "command": "memory.search",
  "data": {
    "count": 2,
    "results": [
      {
        "id": "mem_123",
        "type": "memory",
        "title": "Embeddings strategy",
        "score": 0.91,
        "snippet": "..."
      }
    ]
  },
  "meta": {
    "duration_ms": 38,
    "db": "sqlite",
    "retrieval": ["fts", "vector", "rerank"],
    "view": "compact"
  }
}
```

## Пример ошибки

```json
{
  "ok": false,
  "command": "memory.search",
  "error": {
    "code": "DB_LOCKED",
    "message": "database is locked",
    "retryable": true
  },
  "meta": {
    "duration_ms": 5
  }
}
```
