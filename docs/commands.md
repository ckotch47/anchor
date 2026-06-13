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

- Future write commands such as `notes add` and `tasks add` must reject empty payloads with `INVALID_ARGS`.
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
- Default output should be compact unless `--view full` is requested.

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
- `config get` returns the full effective config plus the resolved config path.
- `config set` writes the updated config back to the user-folder TOML file.

## Current commands

### `anchor health`

- Describes whether the local core is ready and which config/profile was resolved.
- Useful as the first machine check before any agent workflow.

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

### `anchor notes add`

- Creates a note in the shared SQLite core.
- Requires `--title` and `--body`.
- Stores the note through the shared document spine, not a separate memory database.

Example:

```bash
anchor notes add --title "RAG plan" --body "Use SQLite FTS + vector + rerank"
```

### `anchor notes list`

- Returns the newest notes first.
- Use `--limit` to narrow the response.

Example:

```bash
anchor notes list --limit 5
```

### `anchor notes get`

- Returns one note by its document id.
- Use `--id` with the value returned by `notes add` or `notes list`.

Example:

```bash
anchor notes get --id note_123
```

### `anchor notes search`

- Searches note titles and bodies through the shared SQLite retrieval layer.
- Uses FTS over materialized retrieval chunks.
- Chunking stays a separate preprocessing step before retrieval and rerank.
- Search text is normalized before `MATCH`, so special FTS characters are treated as query text, not syntax.
- Search is filtered to the note domain before ranking.
- Start with `--limit` only when you need to trim the response.

Example:

```bash
anchor notes search --query "rag plan" --limit 5
```

## Target command set

- `anchor memory capture`
- `anchor memory search`
- `anchor memory recall`
- `anchor notes add`
- `anchor notes search`
- `anchor tasks add`
- `anchor tasks list`
- `anchor tasks done`
- `anchor history append`
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
- `history` and `tasks` will reuse the same core when their slices land.
- Each domain owns its table(s), while search uses shared document spine + derived retrieval tables.
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
